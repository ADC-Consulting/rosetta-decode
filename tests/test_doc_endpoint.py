"""Tests for GET /jobs/{id}/doc endpoint (S-BE4)."""

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
    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _insert_job(session: AsyncSession, *, doc: str | None = None) -> str:
    job_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    job = Job(
        id=job_id,
        status="done",
        input_hash="abc123",
        files={"test.sas": "data out; set in; run;"},
        doc=doc,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.commit()
    return job_id


@pytest.mark.asyncio
async def test_doc_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/jobs/{uuid.uuid4()}/doc")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_doc_null_when_not_generated(client: AsyncClient, db_session: AsyncSession) -> None:
    job_id = await _insert_job(db_session, doc=None)
    response = await client.get(f"/jobs/{job_id}/doc")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert body["doc"] is None


@pytest.mark.asyncio
async def test_doc_returns_content(client: AsyncClient, db_session: AsyncSession) -> None:
    doc_text = "## Migration Summary\n\nThis script loads `mydata` and filters rows."
    job_id = await _insert_job(db_session, doc=doc_text)
    response = await client.get(f"/jobs/{job_id}/doc")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert body["doc"] == doc_text
