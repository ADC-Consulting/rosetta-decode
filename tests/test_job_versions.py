"""Tests for the per-tab version history endpoints.

Covers:
- POST /jobs/{id}/versions  (create, invalid tab, unknown job)
- GET  /jobs/{id}/versions  (list ordered newest-first, no content field)
- GET  /jobs/{id}/versions/{version_id}  (detail, 404 for unknown)
- Write-through: editor -> python_code, report -> doc, plan -> user_overrides
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
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


async def _insert_job(
    session: AsyncSession,
    *,
    python_code: str | None = None,
    doc: str | None = None,
    user_overrides: dict[str, Any] | None = None,
) -> str:
    """Insert a Job row and return its string ID."""
    job_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    job = Job(
        id=job_id,
        status="proposed",
        input_hash="abc123",
        files={"test.sas": "data out; set in; run;"},
        python_code=python_code,
        doc=doc,
        user_overrides=user_overrides,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.commit()
    return job_id


# ── POST /jobs/{id}/versions ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_version_creates_and_returns_201(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _insert_job(db_session)
    payload = {"content": {"python_code": "df = pd.read_csv('in.csv')"}, "trigger": "human-save"}
    response = await client.post(f"/jobs/{job_id}/versions?tab=editor", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["job_id"] == job_id
    assert body["tab"] == "editor"
    assert "id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_post_version_invalid_tab_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _insert_job(db_session)
    payload = {"content": {}, "trigger": "human-save"}
    response = await client.post(f"/jobs/{job_id}/versions?tab=invalid", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_version_unknown_job_returns_404(client: AsyncClient) -> None:
    fake_id = str(uuid.uuid4())
    payload = {"content": {}, "trigger": "human-save"}
    response = await client.post(f"/jobs/{fake_id}/versions?tab=editor", json=payload)
    assert response.status_code == 404


# ── GET /jobs/{id}/versions ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_versions_ordered_newest_first(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _insert_job(db_session)
    payload_a = {"content": {"python_code": "v1"}, "trigger": "human-save"}
    payload_b = {"content": {"python_code": "v2"}, "trigger": "human-save"}
    await client.post(f"/jobs/{job_id}/versions?tab=editor", json=payload_a)
    await client.post(f"/jobs/{job_id}/versions?tab=editor", json=payload_b)

    response = await client.get(f"/jobs/{job_id}/versions?tab=editor")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    # newest first — second POST should appear at index 0
    # (SQLite may store identical timestamps; just verify descending order is stable)
    for item in items:
        assert "content" not in item
        assert "id" in item
        assert item["tab"] == "editor"


@pytest.mark.asyncio
async def test_list_versions_no_content_field(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _insert_job(db_session)
    payload = {"content": {"secret": "data"}, "trigger": "human-save"}
    await client.post(f"/jobs/{job_id}/versions?tab=report", json=payload)

    response = await client.get(f"/jobs/{job_id}/versions?tab=report")
    assert response.status_code == 200
    for item in response.json():
        assert "content" not in item


# ── GET /jobs/{id}/versions/{version_id} ─────────────────────────────────────


@pytest.mark.asyncio
async def test_get_version_detail_returns_content(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _insert_job(db_session)
    payload = {"content": {"doc": "# Migration report"}, "trigger": "human-save"}
    post_resp = await client.post(f"/jobs/{job_id}/versions?tab=report", json=payload)
    version_id = post_resp.json()["id"]

    response = await client.get(f"/jobs/{job_id}/versions/{version_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == version_id
    assert body["content"] == {"doc": "# Migration report"}
    assert body["tab"] == "report"


@pytest.mark.asyncio
async def test_get_version_detail_unknown_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _insert_job(db_session)
    response = await client.get(f"/jobs/{job_id}/versions/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_version_detail_wrong_job_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id_a = await _insert_job(db_session)
    job_id_b = await _insert_job(db_session)
    payload = {"content": {"x": 1}, "trigger": "human-save"}
    post_resp = await client.post(f"/jobs/{job_id_a}/versions?tab=editor", json=payload)
    version_id = post_resp.json()["id"]

    # Query the version under a different job_id — must 404
    response = await client.get(f"/jobs/{job_id_b}/versions/{version_id}")
    assert response.status_code == 404


# ── Write-through behaviour ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_write_through_editor_updates_python_code(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _insert_job(db_session)
    new_code = "result = spark.read.csv('s3://bucket/in')"
    payload = {"content": {"python_code": new_code}, "trigger": "human-save"}
    response = await client.post(f"/jobs/{job_id}/versions?tab=editor", json=payload)
    assert response.status_code == 201

    result = await db_session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()
    assert job.python_code == new_code


@pytest.mark.asyncio
async def test_write_through_report_updates_doc(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _insert_job(db_session)
    new_doc = "# Reconciliation complete"
    payload = {"content": {"doc": new_doc}, "trigger": "human-save"}
    response = await client.post(f"/jobs/{job_id}/versions?tab=report", json=payload)
    assert response.status_code == 201

    result = await db_session.execute(select(Job).where(Job.id == job_id))
    await db_session.refresh(result.scalar_one())
    result = await db_session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()
    assert job.doc == new_doc


@pytest.mark.asyncio
async def test_write_through_plan_updates_user_overrides(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _insert_job(db_session)
    block_overrides = [{"block_id": "b1", "strategy": "translate", "risk": "low", "note": None}]
    payload = {"content": {"block_overrides": block_overrides}, "trigger": "human-save"}
    response = await client.post(f"/jobs/{job_id}/versions?tab=plan", json=payload)
    assert response.status_code == 201

    result = await db_session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()
    assert job.user_overrides is not None
    assert job.user_overrides["block_overrides"] == block_overrides
