"""Migration package builder for the rosetta-decode backend.

Produces byte-reproducible deployment-ready zip archives from a completed
migration job. The archive contains generated Python source files (mirroring
the original SAS directory tree), a pinned ``requirements.txt``, a
``reconciliation_report.json``, an ``audit.json``, and a human-readable
``migration_summary.md``.

This module MUST NOT import from ``src.worker``.
"""

# SAS: src/backend/api/packaging.py:1

import io
import json
import logging
import re
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Pinned to the runtime this migration was verified against (executor uv.lock).
_RUNTIME_PINS: dict[str, str] = {
    "pyspark": "pyspark==4.1.1",
    "pandas": "pandas==2.3.3",
    "numpy": "numpy==1.26.4",
    "pyarrow": "pyarrow==23.0.1",
    "pyreadstat": "pyreadstat==1.3.4",
}

# Fixed epoch timestamp for reproducible zip archives.
_ZIP_EPOCH = (2000, 1, 1, 0, 0, 0)

_IMPORT_RE = re.compile(
    r"^(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
    re.MULTILINE,
)


def infer_requirements(code_blobs: Iterable[str]) -> list[str]:
    """Infer a pinned requirements list from generated Python code blobs.

    Scans the joined code for top-level imports. ``pyspark`` is always
    included regardless of imports found. Returns a deterministic,
    sorted, de-duplicated list with a provenance header comment.

    Args:
        code_blobs: Iterable of Python source code strings to scan.

    Returns:
        Sorted list of requirement strings, headed by a provenance comment.
    """
    joined = "\n".join(code_blobs)
    top_level_imports = {m.group(1).lower() for m in _IMPORT_RE.finditer(joined)}

    pinned: set[str] = {_RUNTIME_PINS["pyspark"]}
    for lib, pin in _RUNTIME_PINS.items():
        if lib in top_level_imports:
            pinned.add(pin)

    header = "# Pinned to the runtime this migration was verified against (executor uv.lock)."
    return [header, *sorted(pinned)]


def _sas_path_to_module(sas_path: str) -> str:
    """Convert a SAS source path to a mirrored Python module path inside ``src/``.

    Reconstructs a ``src/<dirname>/<stem>.py`` path from a SAS source key
    such as ``sub/dir/foo.sas``. Returns ``src/<stem>.py`` for flat files.

    Args:
        sas_path: Relative SAS file path (e.g. ``sub/dir/foo.sas``).

    Returns:
        Mirrored Python path string (e.g. ``src/sub/dir/foo.py``).
    """
    p = Path(sas_path)
    stem = re.sub(r"[^a-zA-Z0-9_]", "_", p.stem)
    stem = re.sub(r"_+", "_", stem).strip("_") or "block"
    dirpart = str(p.parent)
    if dirpart == ".":
        return f"src/{stem}.py"
    return f"src/{dirpart}/{stem}.py"


def build_audit_record(job: Any, per_block_verification: list[dict[str, Any]]) -> dict[str, Any]:
    """Build an audit record dict for inclusion in ``audit.json``.

    Args:
        job: SQLAlchemy ``Job`` ORM instance.
        per_block_verification: List of per-block verification dicts.

    Returns:
        Dict with job provenance fields and per-block verification list.
    """
    return {
        "job_id": str(job.id),
        "input_hash": job.input_hash,
        "llm_model": job.llm_model,
        "accepted_at": job.accepted_at.isoformat() if job.accepted_at is not None else None,
        "accepted_by": job.accepted_by if job.accepted_by is not None else None,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "per_block_verification": per_block_verification,
    }


def _resolve_src_path(basename: str, files: dict[str, Any] | None) -> str:
    """Resolve the zip archive member path for a generated file.

    Attempts to match a generated file's stem against the original SAS file
    paths to reconstruct the SAS directory tree. Falls back to ``src/<stem>.py``.

    Args:
        basename: Key from ``job.generated_files`` (e.g. ``foo`` or ``foo.py``).
        files: ``job.files`` dict mapping SAS paths to source content.

    Returns:
        Archive member path string (e.g. ``src/sub/dir/foo.py``).
    """
    stem = Path(basename).stem
    if files:
        for sas_path in files:
            if Path(sas_path).stem == stem:
                return _sas_path_to_module(sas_path)
    return f"src/{stem}.py"


def _write_zip_member(zf: zipfile.ZipFile, arcname: str, data: str) -> None:
    """Write a string member with a fixed epoch timestamp for reproducibility.

    Args:
        zf: Open ZipFile to write into.
        arcname: Archive member path.
        data: String content to write.
    """
    info = zipfile.ZipInfo(arcname)
    info.date_time = _ZIP_EPOCH
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, data)


def build_migration_package(job: Any, per_block_verification: list[dict[str, Any]]) -> bytes:
    """Build a byte-reproducible deployment-ready zip archive for a migration job.

    ZIP members (written in sorted order for reproducibility):
    - ``src/**/*.py`` — generated Python files mirroring the SAS directory tree
    - ``audit.json`` — provenance metadata
    - ``migration_summary.md`` — human-readable migration summary
    - ``reconciliation_report.json`` — structured reconciliation results
    - ``requirements.txt`` — pinned runtime dependencies

    Args:
        job: SQLAlchemy ``Job`` ORM instance.
        per_block_verification: Per-block verification dicts for ``audit.json``.

    Returns:
        Zip archive as bytes.
    """
    generated: dict[str, str] = dict(job.generated_files or {})
    files: dict[str, Any] | None = job.files

    # Build src/ members
    src_members: dict[str, str] = {}
    if generated:
        for basename, code in generated.items():
            arcname = _resolve_src_path(basename, files)
            src_members[arcname] = code or ""
    else:
        src_members["src/pipeline.py"] = job.python_code or ""

    all_code = list(src_members.values())
    requirements_lines = infer_requirements(all_code)
    requirements_txt = "\n".join(requirements_lines) + "\n"

    report = job.report or {}
    reconciliation_json = json.dumps(report, indent=2, sort_keys=True)

    audit_dict = build_audit_record(job, per_block_verification)
    audit_json = json.dumps(audit_dict, indent=2, sort_keys=True)

    non_technical_doc: str | None = (
        report.get("non_technical_doc") if isinstance(report, dict) else None
    )
    if non_technical_doc:
        summary_md = non_technical_doc
    elif job.doc:
        summary_md = job.doc
    else:
        summary_md = "No summary available.\n"

    # Collect all members in a dict, then write in sorted order for reproducibility
    members: dict[str, str] = {}
    members.update(src_members)
    members["audit.json"] = audit_json
    members["migration_summary.md"] = summary_md
    members["reconciliation_report.json"] = reconciliation_json
    members["requirements.txt"] = requirements_txt

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname in sorted(members):
            _write_zip_member(zf, arcname, members[arcname])
    buf.seek(0)
    return buf.read()
