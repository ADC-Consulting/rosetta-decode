"""Route tests for GET /jobs/{id}/audit and GET /jobs/{id}/download."""

import io
import json
import uuid
import zipfile
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
    status: str = "queued",
    python_code: str | None = None,
    report: dict[str, Any] | None = None,
    llm_model: str | None = None,
) -> str:
    """Helper — insert a Job row directly and return its ID string."""
    job_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    job = Job(
        id=job_id,
        status=status,
        input_hash="abc123",
        files={"test.sas": "data out; set in; run;"},
        python_code=python_code,
        report=report,
        llm_model=llm_model,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.commit()
    return job_id


# ── GET /jobs/{id} ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_job_happy_path(client: AsyncClient, db_session: AsyncSession) -> None:
    job_id = await _insert_job(db_session, status="queued")
    response = await client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert body["status"] == "queued"
    assert body["python_code"] is None
    assert body["error"] is None


@pytest.mark.asyncio
async def test_get_job_done_with_code(client: AsyncClient, db_session: AsyncSession) -> None:
    job_id = await _insert_job(
        db_session, status="done", python_code="result = df.copy()", report={"checks": []}
    )
    response = await client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["python_code"] == "result = df.copy()"


@pytest.mark.asyncio
async def test_get_job_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/jobs/{uuid.uuid4()}")
    assert response.status_code == 404


# ── Audit endpoint ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_happy_path(client: AsyncClient, db_session: AsyncSession) -> None:
    job_id = await _insert_job(
        db_session,
        status="done",
        report={"checks": []},
        llm_model="anthropic:claude-sonnet-4-6",
    )
    response = await client.get(f"/jobs/{job_id}/audit")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert body["input_hash"] == "abc123"
    assert body["llm_model"] == "anthropic:claude-sonnet-4-6"
    assert body["report"] == {"checks": []}
    assert "created_at" in body
    assert "updated_at" in body


@pytest.mark.asyncio
async def test_audit_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/jobs/{uuid.uuid4()}/audit")
    assert response.status_code == 404


# ── Download endpoint ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_happy_path(client: AsyncClient, db_session: AsyncSession) -> None:
    report = {"checks": [{"name": "row_count", "status": "pass"}]}
    job_id = await _insert_job(
        db_session,
        status="done",
        python_code="print('hello')",
        report=report,
        llm_model="anthropic:claude-sonnet-4-6",
    )
    response = await client.get(f"/jobs/{job_id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert f"rosetta-{job_id}.zip" in response.headers["content-disposition"]

    buf = io.BytesIO(response.content)
    with zipfile.ZipFile(buf) as zf:
        names = zf.namelist()
        assert "pipeline.py" in names
        assert "reconciliation_report.json" in names
        assert "audit.json" in names

        assert zf.read("pipeline.py").decode() == "print('hello')"
        assert json.loads(zf.read("reconciliation_report.json")) == report
        audit = json.loads(zf.read("audit.json"))
        assert audit["job_id"] == job_id
        assert audit["input_hash"] == "abc123"


@pytest.mark.asyncio
async def test_download_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/jobs/{uuid.uuid4()}/download")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_job_not_done(client: AsyncClient, db_session: AsyncSession) -> None:
    job_id = await _insert_job(db_session, status="queued")
    response = await client.get(f"/jobs/{job_id}/download")
    assert response.status_code == 409


# ── Audit: extra field coverage ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_queued_job_has_no_report(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Audit endpoint must still succeed for jobs that haven't finished yet."""
    job_id = await _insert_job(db_session, status="queued")
    response = await client.get(f"/jobs/{job_id}/audit")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert body["report"] is None


@pytest.mark.asyncio
async def test_audit_failed_job(client: AsyncClient, db_session: AsyncSession) -> None:
    """Audit endpoint must work for jobs with status=failed."""
    job_id = await _insert_job(
        db_session,
        status="failed",
        report={"error": "LLM timeout"},
    )
    response = await client.get(f"/jobs/{job_id}/audit")
    assert response.status_code == 200
    body = response.json()
    assert body["report"] == {"error": "LLM timeout"}


# ── Download: zip content detail ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_zip_audit_contains_llm_model(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """audit.json inside the zip must expose the llm_model field."""
    job_id = await _insert_job(
        db_session,
        status="done",
        python_code="pass",
        report={},
        llm_model="anthropic:claude-sonnet-4-6",
    )
    response = await client.get(f"/jobs/{job_id}/download")
    assert response.status_code == 200

    buf = io.BytesIO(response.content)
    with zipfile.ZipFile(buf) as zf:
        audit = json.loads(zf.read("audit.json"))
    assert audit["llm_model"] == "anthropic:claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_download_pipeline_py_exact_content(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """pipeline.py in the zip must be byte-identical to the stored python_code."""
    code = "# Generated by Rosetta Decode\nimport pandas as pd\nresult = df.copy()\n"
    job_id = await _insert_job(
        db_session,
        status="done",
        python_code=code,
        report={},
    )
    response = await client.get(f"/jobs/{job_id}/download")
    assert response.status_code == 200

    buf = io.BytesIO(response.content)
    with zipfile.ZipFile(buf) as zf:
        assert zf.read("pipeline.py").decode() == code
