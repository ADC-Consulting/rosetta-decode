"""Tests for GET /jobs/{id}/plan endpoint with fallback plan handling."""

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Base, Job
from src.backend.db.session import get_async_session
from src.backend.main import app
from src.worker.engine.models import BlockRisk, BlockType, SASBlock
from src.worker.main import _make_fallback_plan

# Use an async SQLite database so tests run without a real PostgreSQL instance
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh in-memory database for each test."""
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
    """Return an AsyncClient wired to the FastAPI app with a test database."""

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_job_plan_returns_plan_when_available(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that endpoint returns the plan when job.migration_plan is present."""
    # Create a job with a migration plan
    job_id = str(uuid.uuid4())
    migration_plan = {
        "summary": "Test plan",
        "overall_risk": "high",
        "block_plans": [],
        "recommended_review_blocks": [],
        "cross_file_dependencies": [],
    }

    job = Job(
        id=job_id,
        status="proposed",
        input_hash="test_hash",
        files={"test.sas": "data a; run;"},
        python_code="# test",
        migration_plan=migration_plan,
    )
    db_session.add(job)
    await db_session.commit()

    # Make request
    response = await client.get(f"/jobs/{job_id}/plan")

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == "Test plan"
    assert data["overall_risk"] == "high"


@pytest.mark.asyncio
async def test_get_job_plan_returns_202_when_plan_unavailable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that endpoint returns 202 when migration_plan is None but job is proposed."""
    # Create a job without a migration plan (agent failed)
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        status="proposed",
        input_hash="test_hash",
        files={"test.sas": "data a; run;"},
        python_code="# test",
        migration_plan=None,  # Plan generation failed
    )
    db_session.add(job)
    await db_session.commit()

    # Make request
    response = await client.get(f"/jobs/{job_id}/plan")

    # Verify response — should be 202, not 404
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "proposed"
    assert "detail" in data
    assert "retry" in data["detail"].lower()


@pytest.mark.asyncio
async def test_get_job_plan_returns_404_for_missing_job(client: AsyncClient) -> None:
    """Test that endpoint returns 404 when job does not exist."""
    job_id = str(uuid.uuid4())
    response = await client.get(f"/jobs/{job_id}/plan")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_job_plan_returns_202_when_job_still_running(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that endpoint returns 202 when job status is queued/running."""
    # Create a running job
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        status="running",
        input_hash="test_hash",
        files={"test.sas": "data a; run;"},
    )
    db_session.add(job)
    await db_session.commit()

    # Make request
    response = await client.get(f"/jobs/{job_id}/plan")

    # Verify 202 for running job
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "running"


def test_make_fallback_plan() -> None:
    """Test fallback plan generation when planning agent fails."""
    from src.worker.engine.models import JobContext

    # Create a minimal context with some blocks
    context = JobContext(
        source_files={"test.sas": "data a; run;"},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        blocks=[
            SASBlock(
                block_type=BlockType.DATA_STEP,
                source_file="test.sas",
                start_line=1,
                end_line=2,
                raw_sas="data a; run;",
            ),
            SASBlock(
                block_type=BlockType.PROC_SORT,
                source_file="test.sas",
                start_line=4,
                end_line=5,
                raw_sas="proc sort data=a; run;",
            ),
        ],
        generated=[],
    )

    plan = _make_fallback_plan(context)

    # Verify fallback plan structure
    assert plan.summary == "Auto-generated fallback plan due to planning agent unavailability."
    assert plan.overall_risk == BlockRisk.HIGH
    assert len(plan.block_plans) == 2
    assert plan.block_plans[0].source_file == "test.sas"
    assert plan.block_plans[0].start_line == 1
    assert all(bp.confidence_score == 0.0 for bp in plan.block_plans)
    assert all(bp.confidence_band == "very_low" for bp in plan.block_plans)
    assert "fallback" in plan.block_plans[0].rationale.lower()
