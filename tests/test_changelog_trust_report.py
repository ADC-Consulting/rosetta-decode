"""Tests for changelog and trust-report endpoints (S6, S7).

Covers:
- GET /jobs/{id}/changelog — empty, newest-first ordering, 404
- GET /jobs/{id}/trust-report — no plan, with plan, 404
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Base, BlockRevision, Job
from src.backend.db.session import get_async_session
from src.backend.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_SAMPLE_PLAN: dict[str, Any] = {
    "summary": "test",
    "overall_risk": "low",
    "recommended_review_blocks": [],
    "cross_file_dependencies": [],
    "block_plans": [
        {
            "block_id": "test.sas:1",
            "source_file": "test.sas",
            "start_line": 1,
            "block_type": "DATA_STEP",
            "strategy": "translate",
            "risk": "low",
            "rationale": "simple",
            "estimated_effort": "1h",
        },
        {
            "block_id": "test.sas:10",
            "source_file": "test.sas",
            "start_line": 10,
            "block_type": "PROC",
            "strategy": "manual",
            "risk": "high",
            "rationale": "complex",
            "estimated_effort": "4h",
        },
    ],
}


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
    status: str = "proposed",
    migration_plan: dict[str, Any] | None = None,
    lineage: dict[str, Any] | None = None,
) -> Job:
    """Create a minimal Job ORM instance for tests."""
    now = datetime.now(UTC)
    return Job(
        id=str(uuid.uuid4()),
        status=status,
        input_hash="abc",
        files={"test.sas": "data out; set in; run;"},
        migration_plan=migration_plan,
        lineage=lineage,
        created_at=now,
        updated_at=now,
    )


def _make_revision(
    job_id: str,
    block_id: str,
    revision_number: int,
    *,
    created_at: datetime | None = None,
) -> BlockRevision:
    """Create a minimal BlockRevision ORM instance for tests."""
    return BlockRevision(
        id=str(uuid.uuid4()),
        job_id=job_id,
        block_id=block_id,
        revision_number=revision_number,
        python_code="pass",
        strategy="translate",
        confidence="high",
        uncertainty_notes=[],
        reconciliation_status="pass",
        trigger="agent",
        created_at=created_at or datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# S6 — changelog tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_changelog_empty(client: AsyncClient, db_session: AsyncSession) -> None:
    """No block revisions returns an empty entries list."""
    job = _make_job()
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/changelog")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job.id
    assert data["entries"] == []


@pytest.mark.asyncio
async def test_changelog_returns_entries_newest_first(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Two revisions are returned newest-first (DESC by created_at)."""
    job = _make_job()
    db_session.add(job)
    await db_session.flush()

    older = datetime.now(UTC) - timedelta(hours=1)
    newer = datetime.now(UTC)

    rev1 = _make_revision(job.id, "test.sas:1", 1, created_at=older)
    rev2 = _make_revision(job.id, "test.sas:1", 2, created_at=newer)
    db_session.add(rev1)
    db_session.add(rev2)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/changelog")
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 2
    # Newest first: revision_number 2 comes before 1
    assert entries[0]["revision_number"] == 2
    assert entries[1]["revision_number"] == 1


@pytest.mark.asyncio
async def test_changelog_job_not_found(client: AsyncClient) -> None:
    """Returns 404 when the job does not exist."""
    response = await client.get(f"/jobs/{uuid.uuid4()}/changelog")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# S7 — trust-report tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trust_report_no_plan(client: AsyncClient, db_session: AsyncSession) -> None:
    """Job with no migration_plan returns empty trust report with status 200."""
    job = _make_job(status="proposed", migration_plan=None)
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/trust-report")
    assert response.status_code == 200
    data = response.json()
    assert data["total_blocks"] == 0
    assert data["overall_confidence"] == "unknown"
    assert data["blocks"] == []
    assert data["review_queue"] == []
    assert data["files"] == []


@pytest.mark.asyncio
async def test_trust_report_with_plan(client: AsyncClient, db_session: AsyncSession) -> None:
    """Job with a migration plan returns correct block-level data."""
    job = _make_job(status="proposed", migration_plan=_SAMPLE_PLAN)
    db_session.add(job)
    await db_session.flush()

    # Add a revision with reconciliation fail for the first block
    rev = BlockRevision(
        id=str(uuid.uuid4()),
        job_id=job.id,
        block_id="test.sas:1",
        revision_number=1,
        python_code="pass",
        strategy="translate",
        confidence="high",
        uncertainty_notes=[],
        reconciliation_status="fail",
        trigger="agent",
        created_at=datetime.now(UTC),
    )
    db_session.add(rev)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/trust-report")
    assert response.status_code == 200
    data = response.json()

    assert data["job_id"] == job.id
    assert data["total_blocks"] == 2
    # The "manual" strategy block counts as manual_todo
    assert data["manual_todo"] == 1
    # The "manual" block should be flagged needs_attention
    assert data["failed_reconciliation"] == 1

    blocks = data["blocks"]
    assert len(blocks) == 2

    # review_queue should contain only needs_attention blocks
    review_queue = data["review_queue"]
    assert all(b["needs_attention"] for b in review_queue)

    # Verify blocks list is sorted: needs_attention DESC (True first)
    if len(blocks) >= 2:
        attention_values = [b["needs_attention"] for b in blocks]
        # All True values should come before False values
        seen_false = False
        for v in attention_values:
            if not v:
                seen_false = True
            elif seen_false:
                pytest.fail("needs_attention ordering violated: False before True")


@pytest.mark.asyncio
async def test_trust_report_job_not_found(client: AsyncClient) -> None:
    """Returns 404 when the job does not exist."""
    response = await client.get(f"/jobs/{uuid.uuid4()}/trust-report")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# _overall_confidence unit tests
# ---------------------------------------------------------------------------


def test_overall_confidence_labels() -> None:
    """_overall_confidence returns correct label for boundary and interior values."""
    from src.backend.api.routes.jobs import _overall_confidence

    assert _overall_confidence(-1.0) == "unknown"
    assert _overall_confidence(0.9) == "high"
    assert _overall_confidence(0.70) == "medium"
    assert _overall_confidence(0.50) == "low"
    assert _overall_confidence(0.30) == "very_low"


# ---------------------------------------------------------------------------
# PlainEnglishAgent.generate unit test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plain_english_agent_generate_returns_doc(monkeypatch: pytest.MonkeyPatch) -> None:
    """PlainEnglishAgent.generate returns the non_technical_doc from the LLM result."""
    from unittest.mock import AsyncMock, MagicMock

    from src.worker.engine.agents.plain_english import PlainEnglishAgent, PlainEnglishResult
    from src.worker.engine.models import JobContext

    fake_result = MagicMock()
    fake_result.output = PlainEnglishResult(non_technical_doc="hello")

    agent = PlainEnglishAgent()
    monkeypatch.setattr(agent._agent, "run", AsyncMock(return_value=fake_result))

    ctx = JobContext(
        source_files={"test.sas": "data out; set in; run;"},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        blocks=[],
        generated=[],
    )
    result = await agent.generate(ctx, python_code="pass", recon_summary="all ok")
    assert result == "hello"


# ── _blast_radius_map direct tests ────────────────────────────────────────────


def test_blast_radius_map_counts_source_blocks() -> None:
    """_blast_radius_map counts outgoing edges per source_block_id."""
    from src.backend.api.routes.jobs import _blast_radius_map

    edges = [
        {"source_block_id": "a.sas:1", "target_block_id": "b.sas:1", "shared_dataset": "x"},
        {"source_block_id": "a.sas:1", "target_block_id": "c.sas:1", "shared_dataset": "y"},
        {"source_block_id": "b.sas:1", "target_block_id": "c.sas:1", "shared_dataset": "z"},
        {"source_block_id": "", "target_block_id": "c.sas:1", "shared_dataset": "w"},
    ]
    result = _blast_radius_map(edges)
    assert result["a.sas:1"] == 2
    assert result["b.sas:1"] == 1
    assert "" not in result


def test_blast_radius_map_empty_list() -> None:
    """_blast_radius_map returns empty dict for empty input."""
    from src.backend.api.routes.jobs import _blast_radius_map

    assert _blast_radius_map([]) == {}


# ── trust-report with cross_file_edges (covers line 1783 branch) ─────────────


@pytest.mark.asyncio
async def test_trust_report_with_multiple_revisions_same_block(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Trust report with multiple BlockRevisions for same block selects latest."""
    import uuid as _uuid

    from src.backend.db.models import BlockRevision

    job_id = str(_uuid.uuid4())
    job = _make_job(
        status="proposed",
        migration_plan=_SAMPLE_PLAN,
        lineage={
            "nodes": [],
            "edges": [],
            "cross_file_edges": [
                {
                    "source_block_id": "test.sas:1",
                    "target_block_id": "other.sas:1",
                    "shared_dataset": "out",
                },
            ],
        },
    )
    job.id = job_id
    db_session.add(job)
    await db_session.commit()

    # Insert two revisions for the same block_id — second one should be used
    for rn, status in ((1, "fail"), (2, "pass")):
        rev = BlockRevision(
            id=str(_uuid.uuid4()),
            job_id=job_id,
            block_id="test.sas:1",
            revision_number=rn,
            python_code=f"# rev {rn}",
            strategy="translate",
            confidence="high",
            trigger="agent",
            reconciliation_status=status,
        )
        db_session.add(rev)
    await db_session.commit()

    response = await client.get(f"/jobs/{job_id}/trust-report")
    assert response.status_code == 200
    data = response.json()
    assert data["total_blocks"] == 2
    # The translate block had revision 2 = pass, manual block has no revision
    translate_blocks = [b for b in data["blocks"] if b["strategy"] == "translate"]
    assert any(b["reconciliation_status"] == "pass" for b in translate_blocks)


# ── _criticality direct tests ─────────────────────────────────────────────────


def test_criticality_manual_strategy() -> None:
    from src.backend.api.routes.jobs import _criticality

    assert _criticality("manual", "high", "pass", 0) == "critical"


def test_criticality_very_low_band() -> None:
    from src.backend.api.routes.jobs import _criticality

    assert _criticality("translate", "very_low", None, None) == "critical"


def test_criticality_high_blast_radius() -> None:
    from src.backend.api.routes.jobs import _criticality

    assert _criticality("translate", "medium", None, 3) == "high"
    assert _criticality("translate", "medium", None, 5) == "high"


def test_criticality_pass_high_confidence() -> None:
    from src.backend.api.routes.jobs import _criticality

    assert _criticality("translate", "high", "pass", 0) == "low"


def test_criticality_human_review_required() -> None:
    from src.backend.api.routes.jobs import _criticality

    assert _criticality("manual", "high", None, None) == "critical"
    assert _criticality("translate", "low", None, None) == "high"
    assert _criticality("translate", "medium", None, None) == "medium"
    assert _criticality("translate", "high", None, 0) == "low"


def test_criticality_recon_fail_is_high() -> None:
    from src.backend.api.routes.jobs import _criticality

    assert _criticality("translate", "high", "fail", 0) == "high"


@pytest.mark.asyncio
async def test_trust_report_blocks_have_criticality_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Trust report response includes criticality and human_review_required per block."""
    import uuid as _uuid

    job_id = str(_uuid.uuid4())
    job = _make_job(status="proposed", migration_plan=_SAMPLE_PLAN)
    job.id = job_id
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/jobs/{job_id}/trust-report")
    assert response.status_code == 200
    data = response.json()
    for block in data["blocks"]:
        assert "criticality" in block
        assert block["criticality"] in ("critical", "high", "medium", "low")
        assert "human_review_required" in block
        assert isinstance(block["human_review_required"], bool)
    manual_blocks = [b for b in data["blocks"] if b["strategy"] == "manual"]
    assert all(b["criticality"] == "critical" for b in manual_blocks)
    assert all(b["human_review_required"] is True for b in manual_blocks)
