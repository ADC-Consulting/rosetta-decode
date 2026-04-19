"""Tests for GET /jobs/{id}/sources endpoint."""

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


@pytest.mark.asyncio
async def test_sources_happy_path(client: AsyncClient, db_session: AsyncSession) -> None:
    """Sources endpoint returns user files and strips sentinel keys."""
    job_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    job = Job(
        id=job_id,
        status="done",
        input_hash="abc123",
        files={"script.sas": "data x; run;", "__ref_sas7bdat__": "/tmp/x"},
        created_at=now,
        updated_at=now,
    )
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job_id}/sources")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert "script.sas" in body["sources"]
    assert body["sources"]["script.sas"] == "data x; run;"
    assert "__ref_sas7bdat__" not in body["sources"]


@pytest.mark.asyncio
async def test_sources_not_found(client: AsyncClient) -> None:
    """Sources endpoint returns 404 for an unknown job."""
    response = await client.get(f"/jobs/{uuid.uuid4()}/sources")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_sources_empty_files(client: AsyncClient, db_session: AsyncSession) -> None:
    """Sources endpoint returns empty dict when job has no files."""
    job_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    job = Job(
        id=job_id,
        status="queued",
        input_hash="abc123",
        files={},
        created_at=now,
        updated_at=now,
    )
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job_id}/sources")
    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == {}
