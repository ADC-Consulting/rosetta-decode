"""Tests for GET /jobs/{id}/lineage endpoint (S-BE3)."""

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

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_SAMPLE_LINEAGE: dict[str, Any] = {
    "job_id": None,  # overridden per-test
    "nodes": [
        {
            "id": "etl.sas::1",
            "label": "DATA_STEP",
            "source_file": "etl.sas",
            "block_type": "DATA_STEP",
            "status": "migrated",
        }
    ],
    "edges": [],
}


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Fresh in-memory database for each test."""
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
    lineage: dict[str, Any] | None = None,
) -> str:
    """Insert a Job row and return its ID string."""
    job_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    job = Job(
        id=job_id,
        status="done",
        input_hash="abc123",
        files={"test.sas": "data out; set in; run;"},
        lineage=lineage,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.commit()
    return job_id


@pytest.mark.asyncio
async def test_lineage_not_found(client: AsyncClient) -> None:
    """Returns 404 when job does not exist."""
    response = await client.get(f"/jobs/{uuid.uuid4()}/lineage")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_lineage_not_yet_computed(client: AsyncClient, db_session: AsyncSession) -> None:
    """Returns 202 with empty body when lineage is None."""
    job_id = await _insert_job(db_session, lineage=None)
    response = await client.get(f"/jobs/{job_id}/lineage")
    assert response.status_code == 202
    assert response.json() == {}


@pytest.mark.asyncio
async def test_lineage_happy_path(client: AsyncClient, db_session: AsyncSession) -> None:
    """Returns 200 with JobLineageResponse when lineage is stored."""
    job_id = await _insert_job(db_session)
    lineage: dict[str, Any] = {
        "job_id": job_id,
        "nodes": [
            {
                "id": "etl.sas::1",
                "label": "DATA_STEP",
                "source_file": "etl.sas",
                "block_type": "DATA_STEP",
                "status": "migrated",
            }
        ],
        "edges": [],
    }
    # Update the row to add lineage directly.
    from sqlalchemy import update as sa_update

    await db_session.execute(sa_update(Job).where(Job.id == job_id).values(lineage=lineage))
    await db_session.commit()

    response = await client.get(f"/jobs/{job_id}/lineage")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["id"] == "etl.sas::1"
    assert body["nodes"][0]["status"] == "migrated"
    assert body["edges"] == []


@pytest.mark.asyncio
async def test_lineage_with_edges(client: AsyncClient, db_session: AsyncSession) -> None:
    """Returns edges correctly when lineage includes them."""
    job_id = await _insert_job(db_session)
    lineage: dict[str, Any] = {
        "job_id": job_id,
        "nodes": [
            {
                "id": "a.sas::1",
                "label": "DATA_STEP",
                "source_file": "a.sas",
                "block_type": "DATA_STEP",
                "status": "migrated",
            },
            {
                "id": "b.sas::5",
                "label": "PROC_SQL",
                "source_file": "b.sas",
                "block_type": "PROC_SQL",
                "status": "migrated",
            },
        ],
        "edges": [
            {
                "source": "a.sas::1",
                "target": "b.sas::5",
                "dataset": "work",
                "inferred": False,
            }
        ],
    }
    from sqlalchemy import update as sa_update

    await db_session.execute(sa_update(Job).where(Job.id == job_id).values(lineage=lineage))
    await db_session.commit()

    response = await client.get(f"/jobs/{job_id}/lineage")
    assert response.status_code == 200
    body = response.json()
    assert len(body["edges"]) == 1
    assert body["edges"][0]["dataset"] == "work"
    assert body["edges"][0]["inferred"] is False
