"""Async route tests for GET /jobs/{id}/runbook (F35 S-F).

Uses an in-memory SQLite database and ASGI test client, following the exact
fixture pattern from tests/test_changelog_trust_report.py.
"""

# SAS: tests/test_runbook_routes.py:1

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Base, BlockRevision, Job
from src.backend.db.session import get_async_session
from src.backend.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# ---------------------------------------------------------------------------
# Sample migration plans
# ---------------------------------------------------------------------------

_PLAN_MANUAL: dict[str, Any] = {
    "summary": "test",
    "overall_risk": "high",
    "recommended_review_blocks": [],
    "cross_file_dependencies": [],
    "block_plans": [
        {
            "block_id": "a.sas:1",
            "source_file": "a.sas",
            "start_line": 1,
            "block_type": "PROC_SQL",
            "strategy": "manual",
            "risk": "high",
            "rationale": "Complex SQL with unsupported SAS extensions.",
            "estimated_effort": "4h",
            "detected_features": ["RETAIN"],
            "input_datasets": ["raw"],
            "output_datasets": ["out"],
        },
    ],
}

_PLAN_HIGH_CONFIDENCE: dict[str, Any] = {
    "summary": "test",
    "overall_risk": "low",
    "recommended_review_blocks": [],
    "cross_file_dependencies": [],
    "block_plans": [
        {
            "block_id": "b.sas:1",
            "source_file": "b.sas",
            "start_line": 1,
            "block_type": "DATA_STEP",
            "strategy": "translated",
            "risk": "low",
            "rationale": "Simple filter.",
            "confidence_band": "high",
            "detected_features": [],
            "input_datasets": ["src"],
            "output_datasets": ["dst"],
        },
        {
            "block_id": "b.sas:20",
            "source_file": "b.sas",
            "start_line": 20,
            "block_type": "PROC",
            "strategy": "translated",
            "risk": "low",
            "rationale": "Simple aggregation.",
            "confidence_band": "high",
            "detected_features": [],
            "input_datasets": [],
            "output_datasets": [],
        },
    ],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Fresh in-memory SQLite database for each test."""
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
    """HTTP test client wired to the in-memory DB."""
    app.dependency_overrides[get_async_session] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _make_job(
    *,
    status: str = "proposed",
    migration_plan: dict[str, Any] | None = None,
    lineage: dict[str, Any] | None = None,
) -> Job:
    """Create a minimal Job ORM instance for tests."""
    now = datetime.now(UTC)
    return Job(
        id=str(uuid.uuid4()),
        status=status,
        input_hash="abc",
        files={"a.sas": "proc sql; quit;"},
        migration_plan=migration_plan,
        lineage=lineage,
        created_at=now,
        updated_at=now,
    )


def _make_revision(
    job_id: str,
    block_id: str,
    revision_number: int,
    *,
    reconciliation_status: str = "pass",
) -> BlockRevision:
    """Create a minimal BlockRevision ORM instance for tests."""
    return BlockRevision(
        id=str(uuid.uuid4()),
        job_id=job_id,
        block_id=block_id,
        revision_number=revision_number,
        python_code="pass",
        strategy="manual",
        confidence="high",
        uncertainty_notes=[],
        reconciliation_status=reconciliation_status,
        trigger="agent",
        created_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runbook_404_on_missing_job(client: AsyncClient) -> None:
    """Returns 404 when the job UUID does not exist."""
    response = await client.get(f"/jobs/{uuid.uuid4()}/runbook")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_runbook_empty_for_queued_job(client: AsyncClient, db_session: AsyncSession) -> None:
    """Job with status 'queued' returns 200 with zero entries."""
    job = _make_job(status="queued", migration_plan=None)
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/runbook")
    assert response.status_code == 200
    data = response.json()
    assert data["total_entries"] == 0
    assert data["entries"] == []


@pytest.mark.asyncio
async def test_runbook_empty_when_no_migration_plan(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Job with status 'proposed' but no migration_plan returns 200 with zero entries."""
    job = _make_job(status="proposed", migration_plan=None)
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/runbook")
    assert response.status_code == 200
    data = response.json()
    assert data["total_entries"] == 0
    assert data["entries"] == []


@pytest.mark.asyncio
async def test_runbook_manual_block_included(client: AsyncClient, db_session: AsyncSession) -> None:
    """A job with a 'manual' strategy block is included in the runbook."""
    job = _make_job(status="proposed", migration_plan=_PLAN_MANUAL)
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/runbook")
    assert response.status_code == 200
    data = response.json()

    assert data["total_entries"] == 1
    entry = data["entries"][0]
    assert entry["block_id"] == "a.sas:1"
    assert entry["criticality"] in ("critical", "high")
    assert isinstance(entry["remediation_outline"], list)
    assert len(entry["remediation_outline"]) > 0
    assert isinstance(entry["why_risky"], list)
    assert len(entry["why_risky"]) > 0
    assert entry["description"] != ""


@pytest.mark.asyncio
async def test_runbook_description_uses_rationale(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """When rationale is set, description uses it."""
    job = _make_job(status="proposed", migration_plan=_PLAN_MANUAL)
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/runbook")
    data = response.json()
    entry = data["entries"][0]
    assert entry["description"] == "Complex SQL with unsupported SAS extensions."


@pytest.mark.asyncio
async def test_runbook_high_confidence_blocks_excluded(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Blocks with 'translated' strategy and high confidence are excluded (total_entries == 0)."""
    job = _make_job(status="proposed", migration_plan=_PLAN_HIGH_CONFIDENCE)
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/runbook")
    assert response.status_code == 200
    data = response.json()
    assert data["total_entries"] == 0


@pytest.mark.asyncio
async def test_runbook_markdown_non_empty_when_entries_exist(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """markdown field is non-empty and contains the runbook header when entries > 0."""
    job = _make_job(status="proposed", migration_plan=_PLAN_MANUAL)
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/runbook")
    data = response.json()
    assert data["total_entries"] > 0
    assert "Remediation Runbook" in data["markdown"]
    assert len(data["markdown"]) > 0


@pytest.mark.asyncio
async def test_runbook_markdown_no_risk_message(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """markdown contains 'no high-risk blocks' message when entries == 0."""
    job = _make_job(status="proposed", migration_plan=_PLAN_HIGH_CONFIDENCE)
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/runbook")
    data = response.json()
    assert data["total_entries"] == 0
    md = data["markdown"].lower()
    assert "no high-risk" in md or "nothing to remediate" in md


@pytest.mark.asyncio
async def test_runbook_includes_block_datasets(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """RunbookEntry includes input_datasets and output_datasets from the block plan."""
    job = _make_job(status="proposed", migration_plan=_PLAN_MANUAL)
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/runbook")
    data = response.json()
    entry = data["entries"][0]
    assert entry["input_datasets"] == ["raw"]
    assert entry["output_datasets"] == ["out"]


@pytest.mark.asyncio
async def test_runbook_recon_fail_block_included(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A translated/high-confidence block with recon fail is included as high criticality."""
    plan: dict[str, Any] = {
        "summary": "test",
        "overall_risk": "low",
        "recommended_review_blocks": [],
        "cross_file_dependencies": [],
        "block_plans": [
            {
                "block_id": "c.sas:1",
                "source_file": "c.sas",
                "start_line": 1,
                "block_type": "DATA_STEP",
                "strategy": "translated",
                "risk": "low",
                "rationale": "Simple step.",
                "confidence_band": "high",
                "detected_features": [],
                "input_datasets": [],
                "output_datasets": [],
            },
        ],
    }
    job = _make_job(status="proposed", migration_plan=plan)
    db_session.add(job)
    await db_session.flush()

    rev = _make_revision(job.id, "c.sas:1", 1, reconciliation_status="fail")
    db_session.add(rev)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/runbook")
    assert response.status_code == 200
    data = response.json()
    assert data["total_entries"] == 1
    assert data["entries"][0]["criticality"] == "high"
    assert data["entries"][0]["reconciliation_status"] == "fail"
