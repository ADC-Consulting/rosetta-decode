"""Tests for POST /jobs/{id}/accept and PATCH /jobs/{id}/plan routes."""

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
    user_overrides: dict[str, Any] | None = None,
) -> str:
    """Insert a Job row directly and return its ID string."""
    job_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    job = Job(
        id=job_id,
        status=status,
        input_hash="abc123",
        files={"test.sas": "data out; set in; run;"},
        python_code=python_code,
        user_overrides=user_overrides,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.commit()
    return job_id


# ── POST /jobs/{id}/accept ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_accept_job_sets_accepted_status(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Happy path: proposed job transitions to accepted."""
    job_id = await _insert_job(db_session, status="proposed")
    response = await client.post(f"/jobs/{job_id}/accept", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["accepted_at"] is not None


@pytest.mark.asyncio
async def test_accept_job_persists_note(client: AsyncClient, db_session: AsyncSession) -> None:
    """Acceptance note is stored in user_overrides."""
    job_id = await _insert_job(db_session, status="proposed")
    response = await client.post(
        f"/jobs/{job_id}/accept", json={"notes": "LGTM — reconciliation passed"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user_overrides"]["acceptance_note"] == "LGTM — reconciliation passed"


@pytest.mark.asyncio
async def test_accept_job_idempotent_on_accepted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Already-accepted job can be re-accepted (status=accepted is in _REVIEW_STATUSES)."""
    job_id = await _insert_job(db_session, status="accepted")
    response = await client.post(f"/jobs/{job_id}/accept", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_accept_job_rejects_queued(client: AsyncClient, db_session: AsyncSession) -> None:
    """Queued job cannot be accepted — returns 409."""
    job_id = await _insert_job(db_session, status="queued")
    response = await client.post(f"/jobs/{job_id}/accept", json={})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_accept_job_rejects_running(client: AsyncClient, db_session: AsyncSession) -> None:
    """Running job cannot be accepted — returns 409."""
    job_id = await _insert_job(db_session, status="running")
    response = await client.post(f"/jobs/{job_id}/accept", json={})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_accept_job_not_found(client: AsyncClient) -> None:
    """Unknown job returns 404."""
    response = await client.post(f"/jobs/{uuid.uuid4()}/accept", json={})
    assert response.status_code == 404


# ── PATCH /jobs/{id}/plan ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_plan_persists_block_overrides(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Block overrides are stored under user_overrides.block_overrides."""
    job_id = await _insert_job(db_session, status="proposed")
    payload = {
        "block_overrides": [
            {"block_id": "block_1", "strategy": "manual", "risk": "high", "note": "review me"}
        ]
    }
    response = await client.patch(f"/jobs/{job_id}/plan", json=payload)
    assert response.status_code == 200
    body = response.json()
    overrides = body["user_overrides"]["block_overrides"]
    assert len(overrides) == 1
    assert overrides[0]["block_id"] == "block_1"
    assert overrides[0]["strategy"] == "manual"


@pytest.mark.asyncio
async def test_patch_plan_merges_block_overrides(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Second PATCH replaces existing block by id and appends new ones."""
    job_id = await _insert_job(
        db_session,
        status="proposed",
        user_overrides={
            "block_overrides": [
                {"block_id": "block_1", "strategy": "translated", "risk": "low", "note": None}
            ]
        },
    )
    payload = {
        "block_overrides": [
            {"block_id": "block_1", "strategy": "manual", "risk": "high", "note": "updated"},
            {"block_id": "block_2", "strategy": "translated", "risk": "low", "note": None},
        ]
    }
    response = await client.patch(f"/jobs/{job_id}/plan", json=payload)
    assert response.status_code == 200
    overrides = response.json()["user_overrides"]["block_overrides"]
    assert len(overrides) == 2
    by_id = {o["block_id"]: o for o in overrides}
    assert by_id["block_1"]["strategy"] == "manual"
    assert by_id["block_2"]["strategy"] == "translated"


@pytest.mark.asyncio
async def test_patch_plan_rejects_failed_job(client: AsyncClient, db_session: AsyncSession) -> None:
    """Failed job cannot have its plan patched — returns 409."""
    job_id = await _insert_job(db_session, status="failed")
    response = await client.patch(f"/jobs/{job_id}/plan", json={"block_overrides": []})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_patch_plan_rejects_queued_job(client: AsyncClient, db_session: AsyncSession) -> None:
    """Queued job cannot have its plan patched — returns 409."""
    job_id = await _insert_job(db_session, status="queued")
    response = await client.patch(f"/jobs/{job_id}/plan", json={"block_overrides": []})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_patch_plan_not_found(client: AsyncClient) -> None:
    """Unknown job returns 404."""
    response = await client.patch(f"/jobs/{uuid.uuid4()}/plan", json={"block_overrides": []})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_plan_translated_with_review_strategy(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """translated_with_review strategy is persisted in block_overrides."""
    job_id = await _insert_job(db_session, status="proposed")
    payload = {
        "block_overrides": [
            {
                "block_id": "block_1",
                "strategy": "translated_with_review",
                "risk": "medium",
                "note": None,
            }
        ]
    }
    response = await client.patch(f"/jobs/{job_id}/plan", json=payload)
    assert response.status_code == 200
    body = response.json()
    overrides = body["user_overrides"]["block_overrides"]
    assert len(overrides) == 1
    assert overrides[0]["strategy"] == "translated_with_review"


@pytest.mark.asyncio
async def test_patch_plan_translate_best_effort_strategy(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """translate_best_effort strategy is persisted in block_overrides."""
    job_id = await _insert_job(db_session, status="proposed")
    payload = {
        "block_overrides": [
            {
                "block_id": "block_2",
                "strategy": "translate_best_effort",
                "risk": "high",
                "note": "PROC IMPORT — verify path",
            }
        ]
    }
    response = await client.patch(f"/jobs/{job_id}/plan", json=payload)
    assert response.status_code == 200
    body = response.json()
    overrides = body["user_overrides"]["block_overrides"]
    assert len(overrides) == 1
    assert overrides[0]["strategy"] == "translate_best_effort"
