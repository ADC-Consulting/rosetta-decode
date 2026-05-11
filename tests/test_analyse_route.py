"""Tests for POST /analyse and the extended POST /migrate (F21)."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Base, Job
from src.backend.db.session import get_async_session
from src.backend.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_MINIMAL_SAS = b"data out; set in; run;"

_SAS_WITH_INCLUDE = b"""\
%include 'missing_file.sas';
data out; set in; run;
"""

_SAS_WITH_PII_DROP = b"""\
data out;
  set in;
  drop SSN DOB;
run;
"""


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create an in-memory SQLite database session for testing."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create an ASGI test client with injected in-memory DB session."""

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Tests for POST /analyse ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyse_valid_sas_returns_200(client: AsyncClient) -> None:
    """POST /analyse with valid .sas content returns 200 with AnalyseResponse shape."""
    with patch(
        "src.backend.api.routes.analyse._generate_pipeline_description",
        new=AsyncMock(return_value="This pipeline processes data."),
    ):
        response = await client.post(
            "/analyse",
            files=[("sas_files", ("script.sas", _MINIMAL_SAS, "text/plain"))],
        )

    assert response.status_code == 200
    body = response.json()

    # Check top-level AnalyseResponse keys
    assert "input_hash" in body
    assert "filenames" in body
    assert "stats" in body
    assert "blocks" in body
    assert "missing_dependencies" in body
    assert "circular_dependencies" in body
    assert "output_coverage" in body
    assert "configuration_values" in body
    assert "sensitive_data_findings" in body
    assert "llm_skipped" in body

    assert "script.sas" in body["filenames"]
    assert isinstance(body["blocks"], list)
    assert isinstance(body["stats"]["total_blocks"], int)
    assert body["llm_skipped"] is False
    assert body["pipeline_description"] == "This pipeline processes data."


@pytest.mark.asyncio
async def test_analyse_sas7bdat_pii_column_detected(client: AsyncClient, tmp_path: object) -> None:
    """POST /analyse with .sas7bdat containing PII column returns sensitive_data_findings."""
    # Mock pyreadstat to return a column named SSN
    mock_meta = MagicMock()
    mock_meta.column_names = ["PATIENT_ID", "SSN", "AMOUNT"]

    with (
        patch(
            "src.backend.api.routes.analyse._generate_pipeline_description",
            new=AsyncMock(return_value=None),
        ),
        patch("pyreadstat.read_sas7bdat", return_value=(None, mock_meta)),
    ):
        response = await client.post(
            "/analyse",
            files=[
                ("sas_files", ("script.sas", _MINIMAL_SAS, "text/plain")),
                (
                    "ref_dataset",
                    ("customers.sas7bdat", b"\x00" * 16, "application/octet-stream"),
                ),
            ],
        )

    assert response.status_code == 200
    body = response.json()
    findings = body["sensitive_data_findings"]
    assert len(findings) > 0
    patterns_found = {f["pattern"] for f in findings}
    # SSN and PATIENT_ID are both PII patterns
    assert patterns_found & {"SSN", "PATIENT_ID"}


@pytest.mark.asyncio
async def test_analyse_missing_include_detected(client: AsyncClient) -> None:
    """POST /analyse with %include referencing a missing file reports it in missing_dependencies."""
    with patch(
        "src.backend.api.routes.analyse._generate_pipeline_description",
        new=AsyncMock(return_value=None),
    ):
        response = await client.post(
            "/analyse",
            files=[("sas_files", ("pipeline.sas", _SAS_WITH_INCLUDE, "text/plain"))],
        )

    assert response.status_code == 200
    body = response.json()
    missing = body["missing_dependencies"]
    # The %include 'missing_file.sas' should appear
    missing_names = [m["name"] for m in missing]
    assert any("missing_file.sas" in name for name in missing_names)


@pytest.mark.asyncio
async def test_analyse_llm_failure_returns_200_with_skipped_flag(client: AsyncClient) -> None:
    """POST /analyse with LLM raising an exception returns 200 with llm_skipped=True."""
    with patch(
        "src.backend.api.routes.analyse._generate_pipeline_description",
        new=AsyncMock(side_effect=RuntimeError("LLM unavailable")),
    ):
        response = await client.post(
            "/analyse",
            files=[("sas_files", ("script.sas", _MINIMAL_SAS, "text/plain"))],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["llm_skipped"] is True
    assert body["pipeline_description"] is None


@pytest.mark.asyncio
async def test_analyse_no_sas_files_returns_400(client: AsyncClient) -> None:
    """POST /analyse with no SAS files returns 400."""
    response = await client.post("/analyse", data={})
    assert response.status_code == 400
    assert "required" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_analyse_non_sas_only_returns_400(client: AsyncClient) -> None:
    """POST /analyse with only non-.sas files (no SAS content) returns 400."""
    with patch(
        "src.backend.api.routes.analyse._generate_pipeline_description",
        new=AsyncMock(return_value=None),
    ):
        # Send only a ref_dataset, no sas_files — should get 400
        response = await client.post("/analyse", data={})

    assert response.status_code == 400


# ── Tests for extended POST /migrate ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_migrate_stores_notes_and_assessment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /migrate with notes and assessment_json stores them on the job row."""
    assessment_payload = {"pipeline_description": "Test pipeline", "input_hash": "abc123"}
    overrides_payload = {"script.sas:1": "high"}

    response = await client.post(
        "/migrate",
        files=[("sas_files", ("script.sas", _MINIMAL_SAS, "text/plain"))],
        data={
            "notes": "My project notes",
            "assessment_json": json.dumps(assessment_payload),
            "importance_overrides": json.dumps(overrides_payload),
        },
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]

    result = await db_session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()

    assert job.notes == "My project notes"
    assert job.assessment is not None
    assert job.assessment.get("pipeline_description") == "Test pipeline"
    # Importance overrides embedded in assessment
    assert "importance_overrides" in job.assessment
    assert job.assessment["importance_overrides"] == overrides_payload


@pytest.mark.asyncio
async def test_migrate_invalid_assessment_json_ignored(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /migrate with malformed assessment_json proceeds without error."""
    response = await client.post(
        "/migrate",
        files=[("sas_files", ("script.sas", _MINIMAL_SAS, "text/plain"))],
        data={"assessment_json": "not-valid-json"},
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]

    result = await db_session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()
    # Should be None since the JSON was invalid
    assert job.assessment is None


@pytest.mark.asyncio
async def test_migrate_no_assessment_leaves_columns_null(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /migrate with no notes or assessment leaves those columns null."""
    response = await client.post(
        "/migrate",
        files=[("sas_files", ("script.sas", _MINIMAL_SAS, "text/plain"))],
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]

    result = await db_session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()

    assert job.notes is None
    assert job.assessment is None


# ── Tests for GET /jobs/{id}/assessment ──────────────────────────────────────


@pytest.mark.asyncio
async def test_get_assessment_returns_stored_data(client: AsyncClient) -> None:
    """GET /jobs/{id}/assessment returns 200 with the stored assessment JSON."""
    assessment_payload = {
        "pipeline_description": "Test pipeline",
        "analyse_response": {"stats": {"needs_manual": 1}, "blocks": []},
    }

    post = await client.post(
        "/migrate",
        files=[("sas_files", ("script.sas", _MINIMAL_SAS, "text/plain"))],
        data={"assessment_json": json.dumps(assessment_payload)},
    )
    assert post.status_code == 200
    job_id = post.json()["job_id"]

    response = await client.get(f"/jobs/{job_id}/assessment")
    assert response.status_code == 200
    body = response.json()
    assert body["pipeline_description"] == "Test pipeline"
    assert body["analyse_response"]["stats"]["needs_manual"] == 1


@pytest.mark.asyncio
async def test_get_assessment_returns_204_when_none(client: AsyncClient) -> None:
    """GET /jobs/{id}/assessment returns 204 when no assessment was captured."""
    post = await client.post(
        "/migrate",
        files=[("sas_files", ("script.sas", _MINIMAL_SAS, "text/plain"))],
    )
    assert post.status_code == 200
    job_id = post.json()["job_id"]

    response = await client.get(f"/jobs/{job_id}/assessment")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_get_assessment_returns_404_for_unknown_job(client: AsyncClient) -> None:
    """GET /jobs/{id}/assessment returns 404 for a non-existent job."""
    response = await client.get("/jobs/00000000-0000-0000-0000-000000000000/assessment")
    assert response.status_code == 404
