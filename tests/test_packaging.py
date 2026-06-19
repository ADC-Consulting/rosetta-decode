"""Unit tests for src/backend/api/packaging.py.

Covers: infer_requirements, build_audit_record, _sas_path_to_module,
build_migration_package — all as pure-function tests with no DB required.
"""

# SAS: tests/test_packaging.py:1

import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from src.backend.api.packaging import (
    _RUNTIME_PINS,
    _sas_path_to_module,
    build_migration_package,
    infer_requirements,
)

# ---------------------------------------------------------------------------
# Minimal fake Job (no DB, no SQLAlchemy)
# ---------------------------------------------------------------------------


@dataclass
class FakeJob:
    """Lightweight stand-in for a SQLAlchemy Job ORM instance."""

    id: str = "test-job-id"
    input_hash: str = "abc123"
    llm_model: str = "anthropic:claude-sonnet-4-6"
    accepted_at: datetime | None = None
    accepted_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime(2024, 1, 1, tzinfo=UTC))
    updated_at: datetime = field(default_factory=lambda: datetime(2024, 1, 1, tzinfo=UTC))
    report: dict[str, Any] | None = None
    doc: str | None = None
    python_code: str | None = None
    generated_files: dict[str, str] | None = None
    files: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _extract_zip(data: bytes) -> dict[str, str]:
    """Return {arcname: text_content} for all members in a zip bytes object."""
    result: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            result[name] = zf.read(name).decode()
    return result


# ---------------------------------------------------------------------------
# build_migration_package — structure
# ---------------------------------------------------------------------------


def test_zip_contains_all_members() -> None:
    """Zip must contain all 5 required members including src/pipeline.py fallback."""
    job = FakeJob()
    members = _extract_zip(build_migration_package(job, []))

    assert "requirements.txt" in members
    assert "reconciliation_report.json" in members
    assert "audit.json" in members
    assert "migration_summary.md" in members
    assert "src/pipeline.py" in members  # fallback when generated_files is empty


# ---------------------------------------------------------------------------
# migration_summary.md content selection
# ---------------------------------------------------------------------------


def test_migration_summary_from_report() -> None:
    """report['non_technical_doc'] takes priority for migration_summary.md."""
    job = FakeJob(
        report={"non_technical_doc": "Non-technical summary text."},
        doc="Fallback doc text.",
    )
    members = _extract_zip(build_migration_package(job, []))

    assert members["migration_summary.md"] == "Non-technical summary text."


def test_migration_summary_fallback_to_doc() -> None:
    """Falls back to job.doc when report has no non_technical_doc key."""
    job = FakeJob(
        report={"checks": []},
        doc="The doc fallback.",
    )
    members = _extract_zip(build_migration_package(job, []))

    assert members["migration_summary.md"] == "The doc fallback."


def test_migration_summary_stub() -> None:
    """Returns a stub string when neither report nor doc is available."""
    job = FakeJob(report=None, doc=None)
    members = _extract_zip(build_migration_package(job, []))

    assert "No summary available" in members["migration_summary.md"]


# ---------------------------------------------------------------------------
# audit.json content
# ---------------------------------------------------------------------------


def test_audit_json_null_pre_accept() -> None:
    """Before acceptance, audit.json has null accepted_at and accepted_by."""
    job = FakeJob(accepted_at=None, accepted_by=None)
    members = _extract_zip(build_migration_package(job, []))

    audit = json.loads(members["audit.json"])
    assert audit["accepted_at"] is None
    assert audit["accepted_by"] is None


def test_audit_json_post_accept() -> None:
    """After acceptance, audit.json carries the real accepted_at and accepted_by."""
    ts = datetime(2024, 6, 17, 12, 0, 0, tzinfo=UTC)
    job = FakeJob(accepted_at=ts, accepted_by="anonymous")
    members = _extract_zip(build_migration_package(job, []))

    audit = json.loads(members["audit.json"])
    assert audit["accepted_at"] == ts.isoformat()
    assert audit["accepted_by"] == "anonymous"
    assert audit["job_id"] == "test-job-id"
    assert audit["input_hash"] == "abc123"


# ---------------------------------------------------------------------------
# infer_requirements
# ---------------------------------------------------------------------------


def test_infer_requirements_always_pyspark() -> None:
    """pyspark is always included even when no code imports it."""
    result = infer_requirements(["x = 1"])

    pins = [r for r in result if not r.startswith("#")]
    assert any("pyspark" in p for p in pins)


def test_infer_requirements_pandas_pin() -> None:
    """Importing pandas in code yields the pandas pin in output."""
    result = infer_requirements(["import pandas as pd\n"])

    pins = [r for r in result if not r.startswith("#")]
    assert any("pandas" in p for p in pins)


def test_infer_requirements_deterministic() -> None:
    """Identical inputs produce byte-for-byte identical sorted output."""
    code = "import pandas\nimport numpy\nfrom pyarrow import Table\n"
    first = infer_requirements([code])
    second = infer_requirements([code])

    assert first == second
    # Must be in sorted order (ignoring the header comment at index 0)
    pins = [r for r in first if not r.startswith("#")]
    assert pins == sorted(pins)


# ---------------------------------------------------------------------------
# Byte reproducibility
# ---------------------------------------------------------------------------


def test_byte_reproducible() -> None:
    """Calling build_migration_package twice with identical input yields identical bytes."""
    job = FakeJob(
        python_code="import pandas\nx = 1\n",
        report={"checks": [{"name": "row_count", "status": "pass"}]},
        doc="My summary.",
    )
    per_block: list[dict[str, Any]] = [
        {"block_id": "step1.sas:1", "reconciliation_status": "pass", "strategy": "translate"},
    ]
    first = build_migration_package(job, per_block)
    second = build_migration_package(job, per_block)

    assert first == second


# ---------------------------------------------------------------------------
# _sas_path_to_module
# ---------------------------------------------------------------------------


def test_sas_path_to_module_flat() -> None:
    """Flat SAS file (no subdirectory) maps to src/<stem>.py."""
    assert _sas_path_to_module("foo.sas") == "src/foo.py"


def test_sas_path_to_module_nested() -> None:
    """Nested SAS file preserves directory structure."""
    assert _sas_path_to_module("sub/dir/bar.sas") == "src/sub/dir/bar.py"


def test_sas_path_to_module_special_chars() -> None:
    """Special characters in stem are replaced with underscores."""
    result = _sas_path_to_module("my-macro.sas")
    assert result == "src/my_macro.py"


# ---------------------------------------------------------------------------
# _RUNTIME_PINS consistency with uv.lock
# ---------------------------------------------------------------------------


def test_pins_in_uv_lock() -> None:
    """Every pin version in _RUNTIME_PINS must appear in uv.lock."""
    repo_root = Path(__file__).parent.parent
    lock_path = repo_root / "uv.lock"
    if not lock_path.exists():
        pytest.skip("uv.lock not present — skipping pin consistency check")

    lock_text = lock_path.read_text()
    for pkg, pin in _RUNTIME_PINS.items():
        version = pin.split("==", 1)[-1]
        assert version in lock_text, (
            f"Package '{pkg}' pinned to '{version}' but that version is not found in uv.lock. "
            f"Run `uv lock` and update _RUNTIME_PINS in packaging.py."
        )
