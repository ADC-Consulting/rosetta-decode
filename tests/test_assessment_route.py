"""Tests for GET /jobs/{id}/assessment — F77 S-D.

Covers:
- Full response: job with a persisted scoping_report → 200, structured report
  fields round-trip and markdown contains expected section headers.
- No scoping report: a normal job (scoping_report=None) → 404.
- Unknown job_id → 404.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Base, Job
from src.backend.db.session import get_async_session
from src.backend.main import app
from src.worker.engine.models import (
    BlockBreakdown,
    DataAssetInventory,
    EffortEstimate,
    FileInventoryItem,
    RiskFlag,
    ScopingReport,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _sample_report() -> ScopingReport:
    """Build a representative ScopingReport for assessment tests."""
    return ScopingReport(
        total_files=2,
        total_lines=240,
        total_blocks=5,
        file_inventory=[
            FileInventoryItem(
                source_file="etl.sas",
                line_count=180,
                block_count=4,
                complexity_tier="moderate",
                block_type_counts={"DATA_STEP": 2, "PROC_SQL": 2},
            ),
            FileInventoryItem(
                source_file="report.sas",
                line_count=60,
                block_count=1,
                complexity_tier="simple",
                block_type_counts={"PROC_PRINT": 1},
            ),
        ],
        block_breakdown=BlockBreakdown(
            counts_by_type={"DATA_STEP": 2, "PROC_SQL": 2, "PROC_PRINT": 1},
            category_by_type={
                "DATA_STEP": "auto_translatable",
                "PROC_SQL": "needs_review",
                "PROC_PRINT": "auto_translatable",
            },
            total_blocks=5,
        ),
        risk_flags=[
            RiskFlag(
                kind="missing_macro",
                severity="high",
                message="Macro %CALC referenced but not defined.",
                detail=["%CALC"],
                count=1,
            ),
        ],
        data_assets=DataAssetInventory(
            libnames=[{"libref": "raw", "engine": "BASE", "path": "/data/raw"}],
            input_datasets=["raw.dm"],
            output_datasets=["work.out"],
            external_file_paths=["/data/in/source.csv"],
        ),
        effort_estimate=EffortEstimate(
            low_days=3.0,
            mid_days=5.0,
            high_days=8.0,
            provisional=True,
            basis="Rule-based from block counts and complexity tiers.",
        ),
        notes=["Macro expansion depth not statically detectable (no silent caps)."],
    )


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
    name: str = "Scope Job",
    status: str = "done",
    scoping_report: dict[str, Any] | None = None,
) -> Job:
    """Create a minimal Job ORM instance for assessment tests."""
    now = datetime.now(UTC)
    return Job(
        id=str(uuid.uuid4()),
        name=name,
        status=status,
        input_hash="deadbeef",
        files={"etl.sas": "data out; set in; run;"},
        scoping_report=scoping_report,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_assessment_full_response(client: AsyncClient, db_session: AsyncSession) -> None:
    """Job with a scoping_report returns 200 with structured report + markdown."""
    job = _make_job(name="ACME Assessment", scoping_report=_sample_report().model_dump())
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/assessment")
    assert response.status_code == 200

    data = response.json()
    assert data["job_id"] == job.id
    assert data["job_name"] == "ACME Assessment"

    # Structured report round-trips a few fields.
    report = data["report"]
    assert report["total_files"] == 2
    assert report["total_blocks"] == 5
    assert report["effort_estimate"]["provisional"] is True
    assert report["effort_estimate"]["mid_days"] == 5.0
    assert report["file_inventory"][0]["source_file"] == "etl.sas"
    assert report["risk_flags"][0]["kind"] == "missing_macro"

    # Markdown present with expected section headers + caveat.
    markdown = data["markdown"]
    assert isinstance(markdown, str)
    assert "# Migration Assessment — ACME Assessment" in markdown
    assert "## File Inventory" in markdown
    assert "## Block Breakdown" in markdown
    assert "## Risk Flags" in markdown
    assert "## Data Asset Inventory" in markdown
    assert "## Effort Estimate" in markdown
    assert "## Notes" in markdown
    assert "PROVISIONAL effort estimate" in markdown


@pytest.mark.asyncio
async def test_assessment_no_report_404(client: AsyncClient, db_session: AsyncSession) -> None:
    """A job without a scoping_report (normal migrate job) returns 404."""
    job = _make_job(name="Migrate Job", status="queued", scoping_report=None)
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/assessment")
    assert response.status_code == 404
    assert "scoping report" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_assessment_unknown_job_404(client: AsyncClient) -> None:
    """Unknown job_id returns 404."""
    unknown_id = str(uuid.uuid4())
    response = await client.get(f"/jobs/{unknown_id}/assessment")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
