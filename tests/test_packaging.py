"""Unit tests for src/backend/api/packaging.py.

Covers: infer_requirements, build_audit_record, _sas_path_to_module,
build_migration_package — all as pure-function tests with no DB required.
Also covers: Databricks Asset Bundle artefact generation (_render_deployment_guide,
new zip members databricks.yml / transformations/*_dlt.py / DEPLOYMENT_GUIDE.md).
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
    _DBX_EXTRA_PINS,
    _RUNTIME_PINS,
    _render_deployment_guide,
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
    migration_plan: dict[str, Any] | None = None
    name: str | None = None
    user_overrides: dict[str, Any] | None = None


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


# ---------------------------------------------------------------------------
# Databricks Asset Bundle artefact generation (S-C)
# ---------------------------------------------------------------------------

_FAKE_BLOCK_PLAN: dict[str, Any] = {
    "block_id": "step1.sas:10",
    "source_file": "step1.sas",
    "start_line": 10,
    "block_type": "DATA",
    "strategy": "translated",
    "risk": "low",
    "rationale": "",
    "estimated_effort": "low",
    "confidence_score": 0.9,
    "confidence_band": "high",
    "input_datasets": ["rawdata"],
    "output_datasets": ["out_ds"],
}

_FAKE_PER_BLOCK_CODE: dict[str, str] = {
    "step1.sas:10": "df = rawdata_df.copy()\nreturn df\n",
}

_FAKE_MIGRATION_PLAN: dict[str, Any] = {
    "block_plans": [_FAKE_BLOCK_PLAN],
}


def _make_dbx_job(**kwargs: Any) -> FakeJob:
    """Return a FakeJob with a minimal migration_plan for DBX artefact tests."""
    return FakeJob(
        id="dbx-job-id",
        name="My Test Job",
        migration_plan=_FAKE_MIGRATION_PLAN,
        **kwargs,
    )


def test_dbx_artefacts_absent_without_per_block_code() -> None:
    """When per_block_code is None (default), DBX artefacts must not appear in the zip."""
    # SAS: tests/test_packaging.py:test_dbx_artefacts_absent_without_per_block_code
    job = _make_dbx_job()
    members = _extract_zip(build_migration_package(job, []))

    assert "databricks.yml" not in members
    assert "DEPLOYMENT_GUIDE.md" not in members
    assert not any(k.startswith("transformations/") for k in members)


def test_dbx_artefacts_absent_without_block_plans() -> None:
    """When migration_plan has no block_plans, DBX artefacts must not appear."""
    # SAS: tests/test_packaging.py:test_dbx_artefacts_absent_without_block_plans
    job = FakeJob(id="no-plan-job", migration_plan={"block_plans": []})
    members = _extract_zip(build_migration_package(job, [], per_block_code=_FAKE_PER_BLOCK_CODE))

    assert "databricks.yml" not in members
    assert "DEPLOYMENT_GUIDE.md" not in members


def test_dbx_artefacts_present_when_block_code_supplied() -> None:
    """When per_block_code is supplied and block_plans exist, all 3 DBX members appear."""
    # SAS: tests/test_packaging.py:test_dbx_artefacts_present_when_block_code_supplied
    job = _make_dbx_job()
    members = _extract_zip(build_migration_package(job, [], per_block_code=_FAKE_PER_BLOCK_CODE))

    assert "databricks.yml" in members
    assert "DEPLOYMENT_GUIDE.md" in members
    assert any(k.startswith("transformations/") and k.endswith("_dlt.py") for k in members)


def test_dbx_pipeline_name_uses_source_file_stem() -> None:
    """The DLT module path uses the slugified SAS source file stem."""
    # SAS: tests/test_packaging.py:test_dbx_pipeline_name_uses_source_file_stem
    job = _make_dbx_job()
    members = _extract_zip(build_migration_package(job, [], per_block_code=_FAKE_PER_BLOCK_CODE))

    # source_file "step1.sas" → "transformations/step1_dlt.py"
    assert "transformations/step1_dlt.py" in members


def test_dbx_existing_five_members_unchanged() -> None:
    """The original 5 zip members must be byte-identical whether or not DBX artefacts are added."""
    # SAS: tests/test_packaging.py:test_dbx_existing_five_members_unchanged
    job = _make_dbx_job(python_code="x = 1\n", doc="Summary.")

    without_dbx = _extract_zip(build_migration_package(job, []))
    with_dbx = _extract_zip(build_migration_package(job, [], per_block_code=_FAKE_PER_BLOCK_CODE))

    core_members = ["audit.json", "migration_summary.md", "reconciliation_report.json"]
    for m in core_members:
        assert without_dbx[m] == with_dbx[m], f"Member {m!r} changed when DBX artefacts were added"

    # src/pipeline.py must be present in both
    assert "src/pipeline.py" in without_dbx
    assert "src/pipeline.py" in with_dbx


def test_dbx_requirements_includes_extra_pins() -> None:
    """When DBX artefacts are added, requirements.txt contains dlt and databricks-sdk pins."""
    # SAS: tests/test_packaging.py:test_dbx_requirements_includes_extra_pins
    job = _make_dbx_job()
    members = _extract_zip(build_migration_package(job, [], per_block_code=_FAKE_PER_BLOCK_CODE))

    req_text = members["requirements.txt"]
    for pin in _DBX_EXTRA_PINS:
        assert pin in req_text, f"Expected pin {pin!r} in requirements.txt"


def test_dbx_requirements_no_extra_pins_without_dbx() -> None:
    """Without DBX artefacts, requirements.txt must NOT contain dlt or databricks-sdk pins."""
    # SAS: tests/test_packaging.py:test_dbx_requirements_no_extra_pins_without_dbx
    job = FakeJob()
    members = _extract_zip(build_migration_package(job, []))

    req_text = members["requirements.txt"]
    assert "dlt==" not in req_text
    assert "databricks-sdk" not in req_text


def test_dbx_byte_reproducible() -> None:
    """build_migration_package with DBX artefacts is byte-reproducible."""
    # SAS: tests/test_packaging.py:test_dbx_byte_reproducible
    job = _make_dbx_job(python_code="x = 1\n", doc="Summary.")

    first = build_migration_package(job, [], per_block_code=_FAKE_PER_BLOCK_CODE)
    second = build_migration_package(job, [], per_block_code=_FAKE_PER_BLOCK_CODE)

    assert first == second


def test_render_deployment_guide_basic() -> None:
    """_render_deployment_guide returns a Markdown string with job_id and pipeline_name."""
    # SAS: tests/test_packaging.py:test_render_deployment_guide_basic
    job = _make_dbx_job()
    guide = _render_deployment_guide(
        job=job,
        schema=[],
        block_plans=_FAKE_MIGRATION_PLAN["block_plans"],
        per_block_code=_FAKE_PER_BLOCK_CODE,
        pipeline_name="rosetta_my_test_job_dlt",
    )

    assert "dbx-job-id" in guide
    assert "rosetta_my_test_job_dlt" in guide
    assert "My Test Job" in guide


def test_render_deployment_guide_untranslatable_block() -> None:
    """Untranslatable blocks appear in the deployment guide's manual migration section."""
    # SAS: tests/test_packaging.py:test_render_deployment_guide_untranslatable_block
    job = _make_dbx_job()
    bad_plan = {
        **_FAKE_BLOCK_PLAN,
        "block_id": "step1.sas:10",
        "output_datasets": ["bad_ds"],
    }
    guide = _render_deployment_guide(
        job=job,
        schema=[],
        block_plans=[bad_plan],
        per_block_code={"step1.sas:10": "# SAS-UNRECOGNIZED\n"},
        pipeline_name="rosetta_my_test_job_dlt",
    )

    assert "Manual migration required" in guide or "manual migration" in guide.lower()
    assert "bad_ds" in guide


# ---------------------------------------------------------------------------
# F75 — packaging reads deployment_target from user_overrides
# ---------------------------------------------------------------------------


def _dbx_members(job: FakeJob) -> dict[str, str]:
    """Build the package and return the extracted DBX members for *job*."""
    return _extract_zip(build_migration_package(job, [], per_block_code=_FAKE_PER_BLOCK_CODE))


def test_dbx_default_no_deployment_target_is_azure_serverless() -> None:
    """No deployment_target → azure/serverless defaults (F74 reproduction)."""
    # SAS: tests/test_packaging.py:test_dbx_default_no_deployment_target_is_azure_serverless
    members = _dbx_members(_make_dbx_job())
    yml = members["databricks.yml"]
    assert "abfss://data@<storage>.dfs.core.windows.net/" in yml
    assert "serverless: true" in yml


def test_dbx_regression_lock_absent_target_equals_default() -> None:
    """REGRESSION LOCK: a job with NO deployment_target produces byte-identical
    databricks.yml and DLT module to the azure/serverless default path."""
    # SAS: tests/test_packaging.py:test_dbx_regression_lock_absent_target_equals_default
    no_target = _dbx_members(_make_dbx_job(user_overrides=None))
    default_target = _dbx_members(
        _make_dbx_job(user_overrides={"deployment_target": {"provider": "azure"}})
    )
    dlt_key = "transformations/step1_dlt.py"
    assert no_target["databricks.yml"] == default_target["databricks.yml"]
    assert no_target[dlt_key] == default_target[dlt_key]


def test_dbx_aws_target_uses_s3_scheme() -> None:
    """An AWS deployment_target threads s3:// into both DBX files."""
    # SAS: tests/test_packaging.py:test_dbx_aws_target_uses_s3_scheme
    members = _dbx_members(_make_dbx_job(user_overrides={"deployment_target": {"provider": "aws"}}))
    dlt_key = "transformations/step1_dlt.py"
    assert "s3://<bucket>/" in members["databricks.yml"]
    assert "s3://<bucket>/" in members[dlt_key]


def test_dbx_classic_compute_emits_cluster_block() -> None:
    """compute_mode=classic emits a placeholder cluster block, not serverless."""
    # SAS: tests/test_packaging.py:test_dbx_classic_compute_emits_cluster_block
    members = _dbx_members(
        _make_dbx_job(user_overrides={"deployment_target": {"compute_mode": "classic"}})
    )
    yml = members["databricks.yml"]
    assert "clusters" in yml
    assert "Standard_DS3_v2" in yml
    assert "serverless: true" not in yml


def test_dbx_catalog_schema_override_in_yml() -> None:
    """catalog/schema answers surface as bundle-variable defaults."""
    # SAS: tests/test_packaging.py:test_dbx_catalog_schema_override_in_yml
    members = _dbx_members(
        _make_dbx_job(
            user_overrides={"deployment_target": {"catalog": "analytics", "schema": "sdtm"}}
        )
    )
    yml = members["databricks.yml"]
    assert "analytics" in yml
    assert "sdtm" in yml


def test_dbx_ingestion_approach_changes_only_the_guide() -> None:
    """ingestion_approach must change the guide but NOT the yml or DLT module."""
    # SAS: tests/test_packaging.py:test_dbx_ingestion_approach_changes_only_the_guide
    historical = _dbx_members(
        _make_dbx_job(user_overrides={"deployment_target": {"ingestion_approach": "historical"}})
    )
    staging = _dbx_members(
        _make_dbx_job(user_overrides={"deployment_target": {"ingestion_approach": "staging"}})
    )
    dlt_key = "transformations/step1_dlt.py"
    assert historical["databricks.yml"] == staging["databricks.yml"]
    assert historical[dlt_key] == staging[dlt_key]
    assert historical["DEPLOYMENT_GUIDE.md"] != staging["DEPLOYMENT_GUIDE.md"]
    assert "cloudFiles" in staging["DEPLOYMENT_GUIDE.md"]
    assert "PROC EXPORT" in historical["DEPLOYMENT_GUIDE.md"]


def test_dbx_byte_reproducible_with_target() -> None:
    """Same deployment_target → identical bytes on a second build."""
    # SAS: tests/test_packaging.py:test_dbx_byte_reproducible_with_target
    job = _make_dbx_job(
        user_overrides={"deployment_target": {"provider": "gcp", "compute_mode": "classic"}}
    )
    first = build_migration_package(job, [], per_block_code=_FAKE_PER_BLOCK_CODE)
    second = build_migration_package(job, [], per_block_code=_FAKE_PER_BLOCK_CODE)
    assert first == second


def test_dbx_guide_includes_provider_auth_host() -> None:
    """The guide prints the provider-specific auth host (AWS example)."""
    # SAS: tests/test_packaging.py:test_dbx_guide_includes_provider_auth_host
    members = _dbx_members(_make_dbx_job(user_overrides={"deployment_target": {"provider": "aws"}}))
    assert "cloud.databricks.com" in members["DEPLOYMENT_GUIDE.md"]


# ---------------------------------------------------------------------------
# F76 — delivery_format dispatch (DLT default vs Classic Spark Job)
# ---------------------------------------------------------------------------

# Portable per-block code (DATA_ROOT-based, result-guaranteed) for spark_job tests.
_PORTABLE_PER_BLOCK_CODE: dict[str, str] = {
    "step1.sas:10": "result = rawdata.withColumn('x', F.lit(1))\n",
}


def _sj_job(**kwargs: Any) -> FakeJob:
    """A DBX job pinned to the spark_job delivery format."""
    overrides = {"deployment_target": {"delivery_format": "spark_job"}}
    overrides["deployment_target"].update(kwargs.pop("dt", {}))
    return _make_dbx_job(user_overrides=overrides, **kwargs)


def _sj_members(job: FakeJob) -> dict[str, str]:
    return _extract_zip(build_migration_package(job, [], per_block_code=_PORTABLE_PER_BLOCK_CODE))


def test_resolver_default_delivery_format_is_dlt() -> None:
    """resolve_deployment_target defaults delivery_format to 'dlt'."""
    # SAS: tests/test_packaging.py:test_resolver_default_delivery_format_is_dlt
    from src.backend.api.databricks_bundle import resolve_deployment_target

    assert resolve_deployment_target(None).delivery_format == "dlt"
    assert resolve_deployment_target({"delivery_format": "bogus"}).delivery_format == "dlt"
    sj = resolve_deployment_target({"delivery_format": "spark_job"})
    assert sj.delivery_format == "spark_job"


def test_spark_job_emits_jobs_modules_not_dlt() -> None:
    """spark_job format → jobs/*.py present, transformations/*_dlt.py absent."""
    # SAS: tests/test_packaging.py:test_spark_job_emits_jobs_modules_not_dlt
    members = _sj_members(_sj_job())
    assert any(k.startswith("jobs/") and k.endswith(".py") for k in members)
    assert not any(k.startswith("transformations/") for k in members)
    assert "jobs/step1/out_ds.py" in members
    assert 'saveAsTable(f"{CATALOG}.{SCHEMA}.out_ds")' in members["jobs/step1/out_ds.py"]


def test_spark_job_yml_has_no_pipelines() -> None:
    """The spark_job databricks.yml carries jobs only, no pipelines resource."""
    # SAS: tests/test_packaging.py:test_spark_job_yml_has_no_pipelines
    import yaml

    members = _sj_members(_sj_job())
    doc = yaml.safe_load(members["databricks.yml"])
    assert "pipelines" not in doc["resources"]
    assert "jobs" in doc["resources"]


def test_spark_job_omits_dlt_pin_keeps_sdk() -> None:
    """spark_job requirements omit the dlt pin but keep databricks-sdk."""
    # SAS: tests/test_packaging.py:test_spark_job_omits_dlt_pin_keeps_sdk
    req = _sj_members(_sj_job())["requirements.txt"]
    assert "dlt==" not in req
    assert "databricks-sdk" in req


def test_spark_job_core_members_identical_to_dlt() -> None:
    """src/audit/recon/summary are identical across delivery formats."""
    # SAS: tests/test_packaging.py:test_spark_job_core_members_identical_to_dlt
    dlt = _dbx_members(_make_dbx_job(python_code="x = 1\n", doc="Summary."))
    sj = _extract_zip(
        build_migration_package(
            _sj_job(python_code="x = 1\n", doc="Summary."),
            [],
            per_block_code=_PORTABLE_PER_BLOCK_CODE,
        )
    )
    core = ["audit.json", "migration_summary.md", "reconciliation_report.json", "src/pipeline.py"]
    for m in core:
        assert dlt[m] == sj[m], f"{m} differs across delivery formats"


def test_spark_job_guide_uses_job_prose() -> None:
    """The spark_job guide branches to Job-task prose + UC Volume prerequisite."""
    # SAS: tests/test_packaging.py:test_spark_job_guide_uses_job_prose
    guide = _sj_members(_sj_job())["DEPLOYMENT_GUIDE.md"]
    assert "one Job task per Delta table" in guide
    assert "Upload source files to the UC Volume" in guide
    assert "@dlt.table` per dataset" not in guide


def test_spark_job_byte_reproducible() -> None:
    """spark_job bundle is byte-reproducible on a second build."""
    # SAS: tests/test_packaging.py:test_spark_job_byte_reproducible
    job = _sj_job(dt={"provider": "aws", "compute_mode": "classic"})
    first = build_migration_package(job, [], per_block_code=_PORTABLE_PER_BLOCK_CODE)
    second = build_migration_package(job, [], per_block_code=_PORTABLE_PER_BLOCK_CODE)
    assert first == second


def test_explicit_dlt_reproduces_default_dlt_bytes() -> None:
    """Explicit delivery_format='dlt' == default (no delivery_format) bytes."""
    # SAS: tests/test_packaging.py:test_explicit_dlt_reproduces_default_dlt_bytes
    default = _dbx_members(_make_dbx_job())
    explicit = _dbx_members(
        _make_dbx_job(user_overrides={"deployment_target": {"delivery_format": "dlt"}})
    )
    dlt_key = "transformations/step1_dlt.py"
    assert default["databricks.yml"] == explicit["databricks.yml"]
    assert default[dlt_key] == explicit[dlt_key]
    assert default["DEPLOYMENT_GUIDE.md"] == explicit["DEPLOYMENT_GUIDE.md"]
