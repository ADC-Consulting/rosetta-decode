"""Migration package builder for the rosetta-decode backend.

Produces byte-reproducible deployment-ready zip archives from a completed
migration job. The archive contains generated Python source files (mirroring
the original SAS directory tree), a pinned ``requirements.txt``, a
``reconciliation_report.json``, an ``audit.json``, and a human-readable
``migration_summary.md``.

When ``per_block_code`` and ``schema`` are supplied, three additional
Databricks Asset Bundle artefacts are included in the zip:
- ``databricks.yml`` — DAB pipeline + job manifest
- ``transformations/<pipeline_name>_dlt.py`` — DLT pipeline module
- ``DEPLOYMENT_GUIDE.md`` — rendered deployment guide

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
from typing import TYPE_CHECKING, Any

import jinja2
from src.backend.api.databricks_bundle import (
    _slugify,
    build_dataset_graph,
    render_databricks_yml,
    render_databricks_yml_spark_job,
    render_dlt_pipeline,
    render_spark_job_modules,
    resolve_deployment_target,
)

if TYPE_CHECKING:
    from src.backend.api.databricks_bundle import DeploymentTarget
    from src.backend.api.schemas import TableSchema

logger = logging.getLogger(__name__)

# Absolute path to the Jinja2 templates directory for this package.
_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Pinned to the runtime this migration was verified against (executor uv.lock).
_RUNTIME_PINS: dict[str, str] = {
    "pyspark": "pyspark==4.1.1",
    "pandas": "pandas==2.3.3",
    "numpy": "numpy==1.26.4",
    "pyarrow": "pyarrow==23.0.1",
    "pyreadstat": "pyreadstat==1.3.4",
}

# Databricks-specific pins added to requirements only when DBX artefacts are present.
# - dlt: Databricks Delta Live Tables API (provided by DBR; not in uv.lock)
# - databricks-sdk: Databricks SDK (in uv.lock; needed for bundle deploy tooling)
# Both are excluded from _RUNTIME_PINS to avoid breaking test_pins_in_uv_lock.
_DBX_EXTRA_PINS: list[str] = [
    "databricks-sdk>=0.24",
    "dlt==0.5.3",
]

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


def _render_deployment_guide(
    job: Any,
    schema: "list[TableSchema]",
    block_plans: list[dict[str, Any]],
    per_block_code: dict[str, str],
    pipeline_name: str,
    target: "DeploymentTarget | None" = None,
    delivery_format: str = "dlt",
) -> str:
    """Render the Databricks deployment guide from the Jinja2 template.

    Builds the ``tables``, ``untranslatable_blocks``, and other template
    variables from the job and schema, then renders
    ``templates/databricks_deployment_guide.md.j2``.

    Args:
        job: ORM ``Job`` instance.
        schema: List of ``TableSchema`` instances.
        block_plans: Normalised block plan list from ``job.migration_plan``.
        per_block_code: Mapping of block_id → generated Python source string.
        pipeline_name: Slugified pipeline name (used as template variable).
        target: Resolved deployment target (F75). Defaults to azure/serverless,
            which reproduces the F74 guide text for jobs with no questionnaire.
        delivery_format: ``dlt`` (default) or ``spark_job`` — branches the prose
            and package-contents table. ``dlt`` stays byte-identical to F75.

    Returns:
        Rendered Markdown string.
    """
    # SAS: src/backend/api/packaging.py:_render_deployment_guide

    # Import locally to avoid a top-level dependency cycle and to obtain the
    # azure/serverless default when no questionnaire answers are present.
    from src.backend.api.databricks_bundle import resolve_deployment_target

    resolved_target = target or resolve_deployment_target(None)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=False,
    )
    template = env.get_template("databricks_deployment_guide.md.j2")

    # Build tables list for the template.
    tables: list[dict[str, Any]] = []
    for ts in schema:
        effective_cols = ts.target_columns or ts.columns
        tables.append(
            {
                "name": ts.dataset_name,
                "target_schema": ts.target_schema,
                "columns": [
                    {"name": c.name, "type": c.override_type or c.semantic_type}
                    for c in effective_cols
                ],
                "pks": [c.name for c in effective_cols if c.is_pk],
            }
        )

    # Build untranslatable_blocks list for the template.
    untranslatable_blocks: list[dict[str, Any]] = []
    for bp in block_plans:
        block_id: str = bp.get("block_id", "")
        output_datasets: list[str] = bp.get("output_datasets", [])
        if not output_datasets:
            continue
        python_code: str = per_block_code.get(block_id, "") or ""
        is_untranslatable = not python_code.strip() or "# SAS-UNRECOGNIZED" in python_code
        if is_untranslatable:
            reason = (
                "SAS-UNRECOGNIZED marker" if "# SAS-UNRECOGNIZED" in python_code else "empty output"
            )
            for output_ds in sorted(output_datasets):
                untranslatable_blocks.append(
                    {
                        "output_dataset": output_ds,
                        "source_file": bp.get("source_file", ""),
                        "line": bp.get("start_line", 0),
                        "reason": reason,
                    }
                )

    raw_name: str = getattr(job, "name", None) or str(job.id)
    job_name = raw_name

    # Per-provider storage-root placeholder for the guide prose. The azure value
    # is byte-identical to the F74 literal so the default guide is unchanged.
    storage_root_placeholders = {
        "azure": "abfss://<container>@<account>.dfs.core.windows.net/<path>/",
        "aws": "s3://<bucket>/<path>/",
        "gcp": "gs://<bucket>/<path>/",
    }

    rendered: str = template.render(
        job_name=job_name,
        job_id=str(job.id),
        tables=tables,
        untranslatable_blocks=untranslatable_blocks,
        catalog_default=resolved_target.catalog,
        storage_root_placeholder=storage_root_placeholders[resolved_target.provider],
        pipeline_name=pipeline_name,
        provider=resolved_target.provider,
        ingestion_approach=resolved_target.ingestion_approach,
        compute_mode=resolved_target.compute_mode,
        auth_host=resolved_target.auth_host,
        storage_scheme=resolved_target.scheme,
        delivery_format=delivery_format,
    )
    return rendered


def build_migration_package(
    job: Any,
    per_block_verification: list[dict[str, Any]],
    per_block_code: dict[str, str] | None = None,
    schema: "list[TableSchema] | None" = None,
) -> bytes:
    """Build a byte-reproducible deployment-ready zip archive for a migration job.

    ZIP members (written in sorted order for reproducibility):
    - ``src/**/*.py`` — generated Python files mirroring the SAS directory tree
    - ``audit.json`` — provenance metadata
    - ``migration_summary.md`` — human-readable migration summary
    - ``reconciliation_report.json`` — structured reconciliation results
    - ``requirements.txt`` — pinned runtime dependencies

    When ``per_block_code`` is non-empty and the job has block plans, three
    additional Databricks Asset Bundle artefacts are appended:
    - ``databricks.yml`` — DAB pipeline + scheduling job manifest
    - ``transformations/<pipeline_name>_dlt.py`` — Delta Live Tables module
    - ``DEPLOYMENT_GUIDE.md`` — rendered deployment guide

    Args:
        job: SQLAlchemy ``Job`` ORM instance.
        per_block_verification: Per-block verification dicts for ``audit.json``.
        per_block_code: Optional mapping of block_id → generated Python source.
            When supplied and non-empty, Databricks artefacts are added to the
            zip. Defaults to ``None`` (no DBX artefacts).
        schema: Optional list of ``TableSchema`` instances for schema-aware DLT
            generation. Defaults to ``None`` (treated as empty list).

    Returns:
        Zip archive as bytes.
    """
    # SAS: src/backend/api/packaging.py:build_migration_package

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

    # ------------------------------------------------------------------
    # Databricks Asset Bundle artefacts (conditional)
    # ------------------------------------------------------------------
    resolved_schema: list[Any] = schema or []
    resolved_per_block_code: dict[str, str] = per_block_code or {}
    plan: dict[str, Any] = job.migration_plan or {}
    block_plans: list[dict[str, Any]] = plan.get("block_plans", [])
    include_dbx = bool(resolved_per_block_code) and bool(block_plans)

    delivery_format = "dlt"
    if include_dbx:
        raw_name: str = getattr(job, "name", None) or str(job.id)
        job_slug = _slugify(raw_name)
        pipeline_name = f"rosetta_{job_slug}_dlt"

        # F75: resolve accept-time questionnaire answers from the existing JSON
        # column. Absent answers (old jobs / pre-accept download) → azure/serverless
        # defaults, which reproduce the F74 bytes exactly.
        user_overrides: dict[str, Any] = getattr(job, "user_overrides", None) or {}
        target = resolve_deployment_target(user_overrides.get("deployment_target"))
        delivery_format = target.delivery_format

        datasets = build_dataset_graph(block_plans)

        if delivery_format == "spark_job":
            # F76: classic multi-task Spark Job bundle (no DLT module).
            job_modules = render_spark_job_modules(
                job, resolved_per_block_code, resolved_schema, target
            )
            databricks_yml = render_databricks_yml_spark_job(job, datasets, resolved_schema, target)
            members.update(job_modules)
            all_code.extend(job_modules.values())
        else:
            dlt_module = render_dlt_pipeline(job, resolved_per_block_code, resolved_schema, target)
            databricks_yml = render_databricks_yml(job, datasets, resolved_schema, target)
            members[f"transformations/{pipeline_name}.py"] = dlt_module
            # Include DLT module in code blobs so the dlt pin is picked up.
            all_code.append(dlt_module)

        deployment_guide = _render_deployment_guide(
            job,
            resolved_schema,
            block_plans,
            resolved_per_block_code,
            pipeline_name,
            target,
            delivery_format,
        )

        members["databricks.yml"] = databricks_yml
        members["DEPLOYMENT_GUIDE.md"] = deployment_guide

    requirements_lines = infer_requirements(all_code)

    # Add Databricks-specific pins explicitly when DBX artefacts are present.
    # dlt and databricks-sdk are not in _RUNTIME_PINS (dlt is not in uv.lock;
    # databricks-sdk top-level import is `databricks` which the scanner can't
    # reliably map to this package name).
    if include_dbx:
        header = (
            requirements_lines[0]
            if requirements_lines and requirements_lines[0].startswith("#")
            else None
        )
        existing_pins = {r for r in requirements_lines if not r.startswith("#")}
        # The dlt pin only applies to the DLT delivery format; the classic Spark
        # Job format uses plain PySpark (keep databricks-sdk for bundle tooling).
        applicable_pins = [
            p for p in _DBX_EXTRA_PINS if delivery_format == "dlt" or not p.startswith("dlt==")
        ]
        extra = {p for p in applicable_pins if p not in existing_pins}
        if extra:
            all_pins = sorted(existing_pins | extra)
            requirements_lines = ([header] if header else []) + all_pins

    requirements_txt = "\n".join(requirements_lines) + "\n"
    members["requirements.txt"] = requirements_txt

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname in sorted(members):
            _write_zip_member(zf, arcname, members[arcname])
    buf.seek(0)
    return buf.read()
