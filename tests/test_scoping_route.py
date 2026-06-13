"""Tests for GET /jobs/{id}/scoping — F34 S-L.

Covers:
- Full response: job with migration_plan + token_usage → 200, all fields populated
- Null token usage: token_usage=None → token_usage and cost are null in response
- Unknown model: token_usage present but model unknown → cost null, token_usage present
- Markdown content: response.markdown contains the job name
- Empty plan: migration_plan=None → BomSummary total_blocks=0, no error
- 404: unknown job_id → 404 response
"""

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

# ---------------------------------------------------------------------------
# Shared fixtures (mirror pattern from test_changelog_trust_report.py)
# ---------------------------------------------------------------------------

_SAMPLE_PLAN: dict[str, Any] = {
    "summary": "test",
    "overall_risk": "medium",
    "recommended_review_blocks": [],
    "cross_file_dependencies": [],
    "block_plans": [
        {
            "block_id": "test.sas:1",
            "source_file": "test.sas",
            "start_line": 1,
            "block_type": "data_step",
            "strategy": "translate",
            "risk": "low",
            "rationale": "simple",
            "estimated_effort": "1h",
        },
        {
            "block_id": "test.sas:10",
            "source_file": "test.sas",
            "start_line": 10,
            "block_type": "proc_sql",
            "strategy": "manual_review",
            "risk": "high",
            "rationale": "complex",
            "estimated_effort": "4h",
        },
        {
            "block_id": "test.sas:20",
            "source_file": "test.sas",
            "start_line": 20,
            "block_type": "macro",
            "strategy": "translate",
            "risk": "medium",
            "rationale": "macro",
            "estimated_effort": "2h",
        },
        {
            "block_id": "test.sas:30",
            "source_file": "test.sas",
            "start_line": 30,
            "block_type": "proc_means",
            "strategy": "untranslatable",
            "risk": "high",
            "rationale": "unsupported",
            "estimated_effort": "8h",
        },
    ],
}

_SAMPLE_TOKEN_USAGE: dict[str, Any] = {
    "phases": {
        "plan": {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_read_tokens": 100,
            "cache_write_tokens": 50,
            "requests": 1,
        },
        "translate": {
            "input_tokens": 2000,
            "output_tokens": 800,
            "cache_read_tokens": 200,
            "cache_write_tokens": 100,
            "requests": 3,
        },
    },
    "total": {
        "input_tokens": 3000,
        "output_tokens": 1300,
        "cache_read_tokens": 300,
        "cache_write_tokens": 150,
        "requests": 4,
    },
}

# A model that is guaranteed to be in the static pricing table.
_KNOWN_MODEL = "anthropic:claude-sonnet-4-6"
# A model name that will never match any pricing entry.
_UNKNOWN_MODEL = "unknown-model-xyz-99"


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
    """HTTP test client wired to the in-memory DB."""
    app.dependency_overrides[get_async_session] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _make_job(
    *,
    name: str = "My Test Job",
    status: str = "proposed",
    migration_plan: dict[str, Any] | None = None,
    token_usage: dict[str, Any] | None = None,
    llm_model: str | None = _KNOWN_MODEL,
) -> Job:
    """Create a minimal Job ORM instance for scoping tests."""
    now = datetime.now(UTC)
    return Job(
        id=str(uuid.uuid4()),
        name=name,
        status=status,
        input_hash="deadbeef",
        files={"test.sas": "data out; set in; run;"},
        migration_plan=migration_plan,
        token_usage=token_usage,
        llm_model=llm_model,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scoping_full_response(client: AsyncClient, db_session: AsyncSession) -> None:
    """Job with migration_plan and token_usage returns 200 with all fields populated."""
    job = _make_job(
        migration_plan=_SAMPLE_PLAN,
        token_usage=_SAMPLE_TOKEN_USAGE,
    )
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/scoping")
    assert response.status_code == 200

    data = response.json()
    assert data["job_id"] == job.id
    assert data["job_name"] == "My Test Job"
    assert data["llm_model"] == _KNOWN_MODEL

    # BOM checks
    bom = data["bom"]
    assert bom["total_blocks"] == 4
    assert bom["data_steps"] == 1
    assert bom["procs"] == 2  # proc_sql + proc_means
    assert bom["macros"] == 1
    assert bom["untranslatable"] == 1  # strategy == "untranslatable"
    # lines 10 (high risk + manual_review) and 30 (high risk + untranslatable) → 2
    assert bom["human_review_required"] == 2
    assert "PROC SQL" in bom["proc_counts"]
    assert "PROC MEANS" in bom["proc_counts"]
    assert bom["risk_buckets"]["low"] == 1
    assert bom["risk_buckets"]["high"] == 2
    assert bom["risk_buckets"]["medium"] == 1
    assert bom["strategy_counts"]["translate"] == 2
    assert bom["strategy_counts"]["manual_review"] == 1
    assert bom["strategy_counts"]["untranslatable"] == 1
    assert isinstance(bom["criticality_buckets"], dict)

    # Token usage present
    assert data["token_usage"] is not None
    assert data["token_usage"]["total"]["input_tokens"] == 3000

    # Cost present (known model)
    assert data["cost"] is not None
    assert data["cost"]["total_usd"] > 0

    # Markdown present
    assert isinstance(data["markdown"], str)
    assert len(data["markdown"]) > 0


@pytest.mark.asyncio
async def test_scoping_null_token_usage(client: AsyncClient, db_session: AsyncSession) -> None:
    """Job with migration_plan but no token_usage returns token_usage=null and cost=null."""
    job = _make_job(migration_plan=_SAMPLE_PLAN, token_usage=None)
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/scoping")
    assert response.status_code == 200

    data = response.json()
    assert data["token_usage"] is None
    assert data["cost"] is None
    # BOM should still be populated
    assert data["bom"]["total_blocks"] == 4


@pytest.mark.asyncio
async def test_scoping_unknown_model_no_cost(client: AsyncClient, db_session: AsyncSession) -> None:
    """Token usage present but unknown model → cost is null, token_usage is present."""
    job = _make_job(
        migration_plan=_SAMPLE_PLAN,
        token_usage=_SAMPLE_TOKEN_USAGE,
        llm_model=_UNKNOWN_MODEL,
    )
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/scoping")
    assert response.status_code == 200

    data = response.json()
    assert data["token_usage"] is not None
    assert data["token_usage"]["total"]["requests"] == 4
    assert data["cost"] is None


@pytest.mark.asyncio
async def test_scoping_markdown_contains_job_name(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """response.markdown must contain the job name."""
    job = _make_job(name="ACME Pipeline", migration_plan=_SAMPLE_PLAN, token_usage=None)
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/scoping")
    assert response.status_code == 200
    assert "ACME Pipeline" in response.json()["markdown"]


@pytest.mark.asyncio
async def test_scoping_empty_plan(client: AsyncClient, db_session: AsyncSession) -> None:
    """Job with migration_plan=None returns BomSummary with total_blocks=0, no error."""
    job = _make_job(migration_plan=None, token_usage=None)
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/scoping")
    assert response.status_code == 200

    bom = response.json()["bom"]
    assert bom["total_blocks"] == 0
    assert bom["data_steps"] == 0
    assert bom["procs"] == 0
    assert bom["macros"] == 0
    assert bom["untranslatable"] == 0
    assert bom["human_review_required"] == 0
    assert bom["proc_counts"] == {}
    assert bom["risk_buckets"] == {}
    assert bom["criticality_buckets"] == {}
    assert bom["strategy_counts"] == {}


@pytest.mark.asyncio
async def test_scoping_404(client: AsyncClient) -> None:
    """Unknown job_id returns 404."""
    unknown_id = str(uuid.uuid4())
    response = await client.get(f"/jobs/{unknown_id}/scoping")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
