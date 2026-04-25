"""Tests for POST /jobs/{job_id}/execute route.

# SAS: tests/test_execute_route.py:1
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Base, Job
from src.backend.db.session import get_async_session
from src.backend.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite session for each test."""
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
    """AsyncClient wired to in-memory DB."""

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def job_with_code(db_session: AsyncSession) -> str:
    """Insert a proposed job with python_code and return its id."""
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        status="proposed",
        input_hash="abc123",
        name="test-job",
        files={},
        python_code="print('hello')",
    )
    db_session.add(job)
    await db_session.commit()
    return job_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _executor_response() -> dict[str, Any]:
    return {
        "stdout": "done\n",
        "stderr": "",
        "result_json": [{"a": 1}],
        "result_columns": ["a"],
        "checks": [{"name": "row_count", "status": "pass"}],
        "error": None,
        "elapsed_ms": 42,
    }


def _mock_executor_client(response_payload: dict[str, Any]) -> Any:
    """Return a context manager mock that posts the given payload."""
    resp_mock = MagicMock()
    resp_mock.json.return_value = response_payload
    resp_mock.raise_for_status = MagicMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_ctx.post = AsyncMock(return_value=resp_mock)
    return mock_ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_route_proxies_executor(
    client: AsyncClient,
    job_with_code: str,
) -> None:
    """A valid job with python_code returns proxied executor response."""
    with patch(
        "src.backend.api.routes.jobs.httpx.AsyncClient",
        return_value=_mock_executor_client(_executor_response()),
    ):
        response = await client.post(f"/jobs/{job_with_code}/execute", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["elapsed_ms"] == 42
    assert body["stdout"] == "done\n"
    assert body["checks"] == [{"name": "row_count", "status": "pass"}]


@pytest.mark.asyncio
async def test_execute_route_404_on_missing_job(client: AsyncClient) -> None:
    """Missing job returns 404."""
    response = await client.post(f"/jobs/{uuid.uuid4()}/execute", json={})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_execute_route_503_on_connect_error(
    client: AsyncClient,
    job_with_code: str,
) -> None:
    """ConnectError from executor returns 503."""
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_ctx.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch("src.backend.api.routes.jobs.httpx.AsyncClient", return_value=mock_ctx):
        resp = await client.post(f"/jobs/{job_with_code}/execute", json={})

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_execute_route_409_no_python_code(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Job with no python_code returns 409."""
    job_id = str(uuid.uuid4())
    db_session.add(Job(id=job_id, status="proposed", input_hash="x", files={}, python_code=None))
    await db_session.commit()

    response = await client.post(f"/jobs/{job_id}/execute", json={})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_execute_route_502_on_http_status_error(
    client: AsyncClient,
    job_with_code: str,
) -> None:
    """HTTPStatusError from executor returns 502."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_ctx.post = AsyncMock(
        side_effect=httpx.HTTPStatusError("err", request=MagicMock(), response=mock_resp)
    )

    with patch("src.backend.api.routes.jobs.httpx.AsyncClient", return_value=mock_ctx):
        resp = await client.post(f"/jobs/{job_with_code}/execute", json={})

    assert resp.status_code == 502
