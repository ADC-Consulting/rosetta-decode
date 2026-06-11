"""Unit tests for block-level refine and revision history endpoints.

# SAS: tests/test_block_refine_routes.py:1
"""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Base, BlockRevision, Job
from src.backend.db.session import get_async_session
from src.backend.main import app
from src.worker.engine.models import BlockType, GeneratedBlock, SASBlock

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


def _make_migration_plan(block_id: str = "test.sas:1") -> dict[str, Any]:
    return {
        "summary": "Test plan",
        "overall_risk": "low",
        "risk_explanation": "",
        "block_plans": [
            {
                "block_id": block_id,
                "source_file": "test.sas",
                "start_line": 1,
                "block_type": "DATA_STEP",
                "strategy": "translate",
                "risk": "low",
                "rationale": "Simple step.",
                "estimated_effort": "low",
                "confidence_score": 0.85,
                "confidence_band": "high",
            }
        ],
        "recommended_review_blocks": [],
        "cross_file_dependencies": [],
    }


async def _insert_proposed_job(
    session: AsyncSession,
    *,
    accepted_at: Any = None,
    status: str = "proposed",
) -> Job:
    """Insert a proposed job with a migration plan."""
    import uuid as _uuid

    job = Job(
        id=str(_uuid.uuid4()),
        status=status,
        input_hash="abc",
        files={"test.sas": "DATA out; SET in; RUN;"},
        migration_plan=_make_migration_plan(),
        accepted_at=accepted_at,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


def _make_fake_generated_block() -> GeneratedBlock:
    sas_block = SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file="test.sas",
        start_line=1,
        end_line=5,
        raw_sas="DATA out; SET in; RUN;",
    )
    return GeneratedBlock(
        source_block=sas_block,
        python_code="out = in_.copy()  # SAS: test.sas:1",
        is_untranslatable=False,
        confidence="high",
        uncertainty_notes=[],
    )


@pytest.mark.asyncio
async def test_refine_block_returns_revision(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST /jobs/{id}/blocks/{block_id}/refine returns revision metadata."""
    job = await _insert_proposed_job(db_session)
    fake_gb = _make_fake_generated_block()

    mock_parse_result = MagicMock()
    mock_parse_result.blocks = [fake_gb.source_block]

    with (
        patch("src.backend.api.routes.jobs._build_translation_router") as mock_build_router,
        patch("src.backend.api.routes.jobs.SASParser") as mock_parser_cls,
        patch(
            "src.backend.api.routes.jobs.asyncio.to_thread",
            new=AsyncMock(return_value={"checks": [{"status": "pass"}]}),
        ),
    ):
        mock_parser_cls.return_value.parse.return_value = mock_parse_result
        mock_router = MagicMock()
        mock_translator = MagicMock()
        mock_translator.translate = AsyncMock(return_value=fake_gb)
        mock_router.route.return_value = mock_translator
        mock_build_router.return_value = mock_router

        response = await client.post(
            f"/jobs/{job.id}/blocks/test.sas%3A1/refine",
            json={"notes": "Fix the join logic"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["block_id"] == "test.sas:1"
    assert data["revision_number"] == 2
    assert data["confidence_band"] == "high"


@pytest.mark.asyncio
async def test_refine_block_404_if_job_missing(
    client: AsyncClient,
) -> None:
    """POST refine returns 404 when job does not exist."""
    response = await client.post(
        "/jobs/00000000-0000-0000-0000-000000000000/blocks/test.sas%3A1/refine",
        json={},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_refine_block_409_if_accepted(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST refine returns 409 when the job has been accepted."""

    from datetime import UTC, datetime

    job = await _insert_proposed_job(db_session, accepted_at=datetime.now(UTC))

    response = await client.post(
        f"/jobs/{job.id}/blocks/test.sas%3A1/refine",
        json={},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_refine_block_404_if_block_not_in_plan(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST refine returns 404 when block_id is not in the migration plan."""
    job = await _insert_proposed_job(db_session)

    response = await client.post(
        f"/jobs/{job.id}/blocks/nonexistent.sas%3A99/refine",
        json={},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_block_revisions_empty(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET revisions returns empty list when no revisions exist."""
    job = await _insert_proposed_job(db_session)

    response = await client.get(f"/jobs/{job.id}/blocks/test.sas%3A1/revisions")

    assert response.status_code == 200
    data = response.json()
    assert data["block_id"] == "test.sas:1"
    assert data["revisions"] == []


@pytest.mark.asyncio
async def test_list_block_revisions_404_if_job_missing(
    client: AsyncClient,
) -> None:
    """GET revisions returns 404 when job does not exist."""
    response = await client.get(
        "/jobs/00000000-0000-0000-0000-000000000000/blocks/test.sas%3A1/revisions"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_block_revisions_returns_history(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET revisions returns stored revisions newest-first."""
    import uuid as _uuid

    job = await _insert_proposed_job(db_session)

    rev = BlockRevision(
        id=str(_uuid.uuid4()),
        job_id=job.id,
        block_id="test.sas:1",
        revision_number=1,
        python_code="out = in_.copy()",
        strategy="translate",
        confidence="high",
        trigger="human-refine",
    )
    db_session.add(rev)
    await db_session.commit()

    response = await client.get(f"/jobs/{job.id}/blocks/test.sas%3A1/revisions")

    assert response.status_code == 200
    data = response.json()
    assert len(data["revisions"]) == 1
    assert data["revisions"][0]["revision_number"] == 1
    assert data["revisions"][0]["confidence_band"] == "high"


@pytest.mark.asyncio
async def test_restore_block_revision_404_if_job_missing(
    client: AsyncClient,
) -> None:
    """POST restore returns 404 when the job does not exist."""
    response = await client.post(
        "/jobs/00000000-0000-0000-0000-000000000000"
        "/blocks/test.sas%3A1/revisions/00000000-0000-0000-0000-000000000001/restore"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_restore_block_revision_409_if_accepted(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST restore returns 409 when the job has been accepted."""
    from datetime import UTC, datetime

    job = await _insert_proposed_job(db_session, accepted_at=datetime.now(UTC))
    response = await client.post(
        f"/jobs/{job.id}/blocks/test.sas%3A1/revisions/00000000-0000-0000-0000-000000000001/restore"
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_restore_block_revision_404_if_revision_missing(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST restore returns 404 when revision does not exist."""
    job = await _insert_proposed_job(db_session)
    response = await client.post(
        f"/jobs/{job.id}/blocks/test.sas%3A1/revisions/00000000-0000-0000-0000-000000000001/restore"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_restore_block_revision_happy_path(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST restore with a valid revision creates a new restore revision."""
    import uuid as _uuid

    job = await _insert_proposed_job(db_session)
    rev_id = str(_uuid.uuid4())
    rev = BlockRevision(
        id=rev_id,
        job_id=job.id,
        block_id="test.sas:1",
        revision_number=1,
        python_code="out = in_.copy()  # original",
        strategy="translate",
        confidence="high",
        trigger="agent",
    )
    db_session.add(rev)
    await db_session.commit()

    response = await client.post(f"/jobs/{job.id}/blocks/test.sas%3A1/revisions/{rev_id}/restore")
    assert response.status_code == 200
    data = response.json()
    assert data["block_id"] == "test.sas:1"
    assert data["revision_number"] == 2


# ─── PATCH /jobs/{job_id}/blocks/{block_id}/python — no existing revision ────


@pytest.mark.asyncio
async def test_save_block_python_no_prior_revision_creates_rev1(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """PATCH python with no prior revision creates revision_number=1."""
    job = await _insert_proposed_job(db_session)

    response = await client.patch(
        f"/jobs/{job.id}/blocks/test.sas%3A1/python",
        json={"python_code": "out = in_.copy()  # human edit", "notes": "My fix"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["revision_number"] == 1
    assert data["block_id"] == "test.sas:1"


# ─── POST /jobs/{job_id}/blocks/{block_id}/refine — 404 invalid block_id ─────


@pytest.mark.asyncio
async def test_refine_block_404_no_colon_in_block_id(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST refine returns 404 when block_id has no colon separator."""
    job = await _insert_proposed_job(db_session)

    # block_id without colon
    response = await client.post(
        f"/jobs/{job.id}/blocks/nocolon/refine",
        json={},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_refine_block_404_source_file_missing(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST refine returns 404 when source_file is not in job.files."""
    job = await _insert_proposed_job(db_session)

    # block_id references a file not in job.files
    response = await client.post(
        f"/jobs/{job.id}/blocks/nonexistent_file.sas%3A1/refine",
        json={},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_refine_block_404_block_not_in_parse_result(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST refine returns 404 when block start_line is not found in parse result."""
    job = await _insert_proposed_job(db_session)

    mock_parse_result = MagicMock()
    mock_parse_result.blocks = []  # no blocks at all

    with patch("src.backend.api.routes.jobs.SASParser") as mock_parser_cls:
        mock_parser_cls.return_value.parse.return_value = mock_parse_result
        response = await client.post(
            f"/jobs/{job.id}/blocks/test.sas%3A999/refine",
            json={},
        )

    assert response.status_code == 404


# ─── BlockPythonEditRequest.trigger validation ───────────────────────────────

# SAS: tests/test_block_refine_routes.py:407


def test_block_python_edit_request_trigger_defaults_to_human() -> None:
    """BlockPythonEditRequest.trigger defaults to 'human' when omitted."""
    from src.backend.api.schemas import BlockPythonEditRequest

    req = BlockPythonEditRequest(python_code="x = 1")
    assert req.trigger == "human"


def test_block_python_edit_request_trigger_accepts_all_allowed_values() -> None:
    """BlockPythonEditRequest.trigger accepts every value in the allowlist."""
    from src.backend.api.schemas import BlockPythonEditRequest

    for value in ("human", "human-verify", "human-refine"):
        req = BlockPythonEditRequest(python_code="x = 1", trigger=value)
        assert req.trigger == value


def test_block_python_edit_request_trigger_rejects_unknown_value() -> None:
    """BlockPythonEditRequest.trigger raises ValueError for unknown triggers."""
    import pytest
    from pydantic import ValidationError
    from src.backend.api.schemas import BlockPythonEditRequest

    with pytest.raises(ValidationError):
        BlockPythonEditRequest(python_code="x = 1", trigger="agent")


# ─── PATCH /jobs/{job_id}/blocks/{block_id}/python — trigger forwarded ────────


@pytest.mark.asyncio
async def test_save_block_python_forwards_trigger_to_revision(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """PATCH python with trigger='human-verify' stores that value on the revision."""
    job = await _insert_proposed_job(db_session)

    response = await client.patch(
        f"/jobs/{job.id}/blocks/test.sas%3A1/python",
        json={
            "python_code": "out = in_.copy()  # verified",
            "notes": "Verified by reviewer",
            "trigger": "human-verify",
        },
    )
    assert response.status_code == 200

    from sqlalchemy import select
    from src.backend.db.models import BlockRevision

    stmt = select(BlockRevision).where(BlockRevision.job_id == str(job.id))
    result = await db_session.execute(stmt)
    revision = result.scalars().first()
    assert revision is not None
    assert revision.trigger == "human-verify"


@pytest.mark.asyncio
async def test_refine_block_second_refine_increments_revision(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST refine on a block that already has revisions increments revision_number."""
    import uuid as _uuid

    job = await _insert_proposed_job(db_session)
    fake_gb = _make_fake_generated_block()

    # Pre-insert two revisions to simulate previous refines
    for rn in (1, 2):
        rev = BlockRevision(
            id=str(_uuid.uuid4()),
            job_id=job.id,
            block_id="test.sas:1",
            revision_number=rn,
            python_code=f"out = in_.copy()  # rev {rn}",
            strategy="translate",
            confidence="high",
            trigger="human-refine",
        )
        db_session.add(rev)
    await db_session.commit()

    mock_parse_result = MagicMock()
    mock_parse_result.blocks = [fake_gb.source_block]

    with (
        patch("src.backend.api.routes.jobs._build_translation_router") as mock_build_router,
        patch("src.backend.api.routes.jobs.SASParser") as mock_parser_cls,
        patch(
            "src.backend.api.routes.jobs.asyncio.to_thread",
            new=AsyncMock(return_value={"checks": [{"status": "pass"}]}),
        ),
    ):
        mock_parser_cls.return_value.parse.return_value = mock_parse_result
        mock_router = MagicMock()
        mock_translator = MagicMock()
        mock_translator.translate = AsyncMock(return_value=fake_gb)
        mock_router.route.return_value = mock_translator
        mock_build_router.return_value = mock_router

        response = await client.post(
            f"/jobs/{job.id}/blocks/test.sas%3A1/refine",
            json={},
        )

    assert response.status_code == 200
    data = response.json()
    # With 2 existing revisions, max is rev 2, so next should be 3
    assert data["revision_number"] == 3
