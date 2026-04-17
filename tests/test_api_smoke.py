"""Smoke tests for the backend API using an in-memory SQLite database."""

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Base
from src.backend.db.session import get_async_session
from src.backend.main import app

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
async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_migrate_creates_job(client: AsyncClient) -> None:
    sas_content = b"data work.out; set work.in; run;"
    response = await client.post(
        "/migrate",
        files=[("sas_files", ("sample.sas", sas_content, "text/plain"))],
    )
    assert response.status_code == 200
    body = response.json()
    assert "job_id" in body
    # Should be a valid UUID
    uuid.UUID(body["job_id"])


@pytest.mark.asyncio
async def test_get_job_status(client: AsyncClient) -> None:
    sas_content = b"proc sql; select * from work.src; quit;"
    create = await client.post(
        "/migrate",
        files=[("sas_files", ("script.sas", sas_content, "text/plain"))],
    )
    job_id = create.json()["job_id"]

    response = await client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert body["status"] == "queued"
    assert body["python_code"] is None
    assert body["error"] is None


@pytest.mark.asyncio
async def test_get_job_not_found(client: AsyncClient) -> None:
    missing_id = uuid.uuid4()
    response = await client.get(f"/jobs/{missing_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_migrate_rejects_non_sas(client: AsyncClient) -> None:
    response = await client.post(
        "/migrate",
        files=[("sas_files", ("report.csv", b"col1,col2\n1,2", "text/plain"))],
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_migrate_rejects_empty(client: AsyncClient) -> None:
    response = await client.post("/migrate", files=[])
    assert response.status_code in (400, 422)
