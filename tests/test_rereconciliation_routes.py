"""Tests for PUT /jobs/{id}/python_code, POST /jobs/{id}/refine, GET /jobs/{id}/history."""

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Base, Job
from src.backend.db.session import get_async_session
from src.backend.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


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
    """AsyncClient wired to the FastAPI app with an in-memory test database."""

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _insert_job(
    session: AsyncSession,
    *,
    status: str = "queued",
    python_code: str | None = None,
    parent_job_id: str | None = None,
    trigger: str = "agent",
    skip_llm: bool = False,
    files: dict[str, str] | None = None,
) -> str:
    """Insert a Job row directly and return its ID string."""
    job_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    job = Job(
        id=job_id,
        status=status,
        input_hash="abc123",
        files=files if files is not None else {"test.sas": "data out; set in; run;"},
        python_code=python_code,
        parent_job_id=parent_job_id,
        trigger=trigger,
        skip_llm=skip_llm,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.commit()
    return job_id


# ── PUT /jobs/{id}/python_code ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_python_code_happy_path(client: AsyncClient, db_session: AsyncSession) -> None:
    """PUT updates code, sets status=queued, skip_llm=True, trigger=human-rereconcile."""
    job_id = await _insert_job(db_session, status="proposed", python_code="old_code")
    new_code = "df = df.sort_values(by=['id'])  # SAS: test.sas:1"
    response = await client.put(
        f"/jobs/{job_id}/python_code",
        json={"python_code": new_code},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["python_code"] == new_code
    assert body["skip_llm"] is True
    assert body["trigger"] == "human-rereconcile"
    assert body["report"] is None


@pytest.mark.asyncio
async def test_put_python_code_409_on_running(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Returns 409 when the job is currently running."""
    job_id = await _insert_job(db_session, status="running")
    response = await client.put(
        f"/jobs/{job_id}/python_code",
        json={"python_code": "x = 1"},
    )
    assert response.status_code == 409
    assert "running" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_put_python_code_404_on_missing(client: AsyncClient) -> None:
    """Returns 404 for an unknown job ID."""
    response = await client.put(
        f"/jobs/{uuid.uuid4()}/python_code",
        json={"python_code": "x = 1"},
    )
    assert response.status_code == 404


# ── POST /jobs/{id}/refine ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refine_creates_child_job(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /refine creates a child job with parent_job_id set and returns RefineResponse."""
    parent_id = await _insert_job(db_session, status="proposed", python_code="# v1")
    response = await client.post(
        f"/jobs/{parent_id}/refine",
        json={"hint": "Fix the date column"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "job_id" in body
    child_id = body["job_id"]
    assert child_id != parent_id

    # Verify the child was persisted
    get_resp = await client.get(f"/jobs/{child_id}")
    assert get_resp.status_code == 200
    child = get_resp.json()
    assert child["parent_job_id"] == parent_id
    assert child["trigger"] == "human-refine"
    assert child["status"] == "queued"


@pytest.mark.asyncio
async def test_refine_works_on_failed_job(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /refine succeeds even when the parent job status is 'failed'."""
    parent_id = await _insert_job(db_session, status="failed")
    response = await client.post(f"/jobs/{parent_id}/refine", json={})
    assert response.status_code == 200
    assert "job_id" in response.json()


@pytest.mark.asyncio
async def test_refine_injects_context_sentinel(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """New child job has __refine_context__ sentinel in files with prior code and hint."""
    parent_id = await _insert_job(db_session, status="proposed", python_code="# prior code")
    response = await client.post(
        f"/jobs/{parent_id}/refine",
        json={"hint": "use merge instead of concat"},
    )
    assert response.status_code == 200
    child_id = response.json()["job_id"]

    # Load child directly from db to inspect files
    from sqlalchemy import select

    result = await db_session.execute(select(Job).where(Job.id == child_id))
    child_job = result.scalar_one()

    assert "__refine_context__" in child_job.files
    ctx = json.loads(child_job.files["__refine_context__"])
    assert ctx["prior_python_code"] == "# prior code"
    assert ctx["hint"] == "use merge instead of concat"


@pytest.mark.asyncio
async def test_refine_404_on_missing_parent(client: AsyncClient) -> None:
    """Returns 404 for an unknown parent job ID."""
    response = await client.post(f"/jobs/{uuid.uuid4()}/refine", json={})
    assert response.status_code == 404


# ── GET /jobs/{id}/history ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_history_single_job(client: AsyncClient, db_session: AsyncSession) -> None:
    """Single job with no parent or children returns a history with one entry, is_current=True."""
    job_id = await _insert_job(db_session, status="proposed")
    response = await client.get(f"/jobs/{job_id}/history")
    assert response.status_code == 200
    body = response.json()
    assert len(body["entries"]) == 1
    entry = body["entries"][0]
    assert entry["job_id"] == job_id
    assert entry["is_current"] is True
    assert entry["trigger"] == "agent"


@pytest.mark.asyncio
async def test_history_chain(client: AsyncClient, db_session: AsyncSession) -> None:
    """Parent → child chain returns 2 entries sorted oldest-first."""
    parent_id = await _insert_job(db_session, status="proposed", trigger="agent")
    child_id = await _insert_job(
        db_session,
        status="queued",
        trigger="human-refine",
        parent_job_id=parent_id,
    )

    # Query from the child's perspective
    response = await client.get(f"/jobs/{child_id}/history")
    assert response.status_code == 200
    body = response.json()
    entries = body["entries"]
    assert len(entries) == 2

    # Oldest first → parent should be first
    assert entries[0]["job_id"] == parent_id
    assert entries[0]["is_current"] is False
    assert entries[1]["job_id"] == child_id
    assert entries[1]["is_current"] is True


@pytest.mark.asyncio
async def test_history_404_on_missing(client: AsyncClient) -> None:
    """Returns 404 for an unknown job ID."""
    response = await client.get(f"/jobs/{uuid.uuid4()}/history")
    assert response.status_code == 404
