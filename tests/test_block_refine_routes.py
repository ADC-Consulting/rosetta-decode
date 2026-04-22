"""Tests for block-level refine and revision history endpoints.

Covers:
- POST /jobs/{id}/blocks/{block_id}/refine — happy path, 404, 409 (accepted job)
- POST /jobs/{id}/refine — 409 guard when job is accepted
- GET /jobs/{id}/blocks/{block_id}/revisions — list and empty
- POST /jobs/{id}/blocks/{block_id}/revisions/{revision_id}/restore — happy path, 404
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
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

_SAMPLE_SAS = "data out; set in; run;"
_SAMPLE_BLOCK_ID = "test.sas:1"

_FAKE_GB = GeneratedBlock(
    source_block=SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file="test.sas",
        start_line=1,
        end_line=1,
        raw_sas=_SAMPLE_SAS,
    ),
    python_code="# SAS: test.sas:1\nout = in_.copy()\n",
    confidence="high",
    uncertainty_notes=[],
)


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
    """AsyncClient wired to the FastAPI app with in-memory DB."""

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
    status: str = "proposed",
    python_code: str | None = "# SAS: test.sas:1\nout = in_.copy()\n",
    accepted_at: datetime | None = None,
    files: dict[str, Any] | None = None,
) -> str:
    """Insert a Job row and return its string ID."""
    job_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    job = Job(
        id=job_id,
        status=status,
        input_hash="abc123",
        files=files or {"test.sas": _SAMPLE_SAS},
        python_code=python_code,
        accepted_at=accepted_at,
        trigger="agent",
        skip_llm=False,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.commit()
    return job_id


# ── POST /jobs/{id}/blocks/{block_id}/refine ──────────────────────────────────


@pytest.mark.asyncio
async def test_refine_block_happy_path(client: AsyncClient, db_session: AsyncSession) -> None:
    """Refining a block translates it, inserts revisions, and returns 200."""
    job_id = await _insert_job(db_session)

    mock_translator = AsyncMock()
    mock_translator.translate = AsyncMock(return_value=_FAKE_GB)

    mock_router = MagicMock()
    mock_router.route.return_value = mock_translator

    mock_recon_report = {"checks": [{"name": "row_count", "status": "pass"}]}

    with (
        patch("src.backend.api.routes.jobs._build_translation_router", return_value=mock_router),
        patch("asyncio.to_thread", new=AsyncMock(return_value=mock_recon_report)),
    ):
        resp = await client.post(
            f"/jobs/{job_id}/blocks/test.sas%3A1/refine",
            json={"notes": "use copy instead of merge"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["block_id"] == "test.sas:1"
    assert body["revision_number"] == 2  # first refine creates rev 1 (prior) + rev 2 (new)
    assert body["confidence"] == "high"
    assert body["reconciliation_status"] == "pass"


@pytest.mark.asyncio
async def test_refine_block_subsequent_refine(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Subsequent refines increment revision_number without inserting a prior revision."""
    job_id = await _insert_job(db_session)

    # Pre-insert revision 1 and 2 to simulate a prior refine
    now = datetime.now(UTC)
    for rev_num in [1, 2]:
        session_rev = BlockRevision(
            id=str(uuid.uuid4()),
            job_id=job_id,
            block_id="test.sas:1",
            revision_number=rev_num,
            python_code="# SAS: test.sas:1\nold = src.copy()\n",
            strategy="translate",
            confidence="high",
            uncertainty_notes=[],
            trigger="agent" if rev_num == 1 else "human-refine",
            created_at=now,
        )
        db_session.add(session_rev)
    await db_session.commit()

    mock_translator = AsyncMock()
    mock_translator.translate = AsyncMock(return_value=_FAKE_GB)
    mock_router = MagicMock()
    mock_router.route.return_value = mock_translator

    with (
        patch("src.backend.api.routes.jobs._build_translation_router", return_value=mock_router),
        patch("asyncio.to_thread", new=AsyncMock(return_value={"checks": []})),
    ):
        resp = await client.post(
            f"/jobs/{job_id}/blocks/test.sas%3A1/refine",
            json={},
        )

    assert resp.status_code == 200
    assert resp.json()["revision_number"] == 3


@pytest.mark.asyncio
async def test_refine_block_job_not_found(client: AsyncClient) -> None:
    """Refining a block on a non-existent job returns 404."""
    resp = await client.post(f"/jobs/{uuid.uuid4()}/blocks/test.sas%3A1/refine", json={})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_refine_block_accepted_job_returns_409(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Refining a block on an accepted job returns 409."""
    job_id = await _insert_job(db_session, accepted_at=datetime.now(UTC))
    resp = await client.post(f"/jobs/{job_id}/blocks/test.sas%3A1/refine", json={})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_refine_block_source_file_not_found(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Refining a block whose source file is missing from job.files returns 404."""
    job_id = await _insert_job(db_session, files={"other.sas": "data x; run;"})
    resp = await client.post(f"/jobs/{job_id}/blocks/test.sas%3A1/refine", json={})
    assert resp.status_code == 404


# ── POST /jobs/{id}/refine — 409 guard ───────────────────────────────────────


@pytest.mark.asyncio
async def test_whole_job_refine_accepted_returns_409(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /jobs/{id}/refine returns 409 when the job has been accepted."""
    job_id = await _insert_job(db_session, accepted_at=datetime.now(UTC))
    resp = await client.post(f"/jobs/{job_id}/refine", json={})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_whole_job_refine_not_accepted_succeeds(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /jobs/{id}/refine creates a child job when the job is not accepted."""
    job_id = await _insert_job(db_session, accepted_at=None)
    resp = await client.post(f"/jobs/{job_id}/refine", json={"hint": "be more explicit"})
    assert resp.status_code == 200
    assert "job_id" in resp.json()


# ── GET /jobs/{id}/blocks/{block_id}/revisions ───────────────────────────────


@pytest.mark.asyncio
async def test_get_block_revisions_empty(client: AsyncClient, db_session: AsyncSession) -> None:
    """GET revisions returns empty list when no revisions exist."""
    job_id = await _insert_job(db_session)
    resp = await client.get(f"/jobs/{job_id}/blocks/test.sas%3A1/revisions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["block_id"] == "test.sas:1"
    assert body["revisions"] == []


@pytest.mark.asyncio
async def test_get_block_revisions_sorted_desc(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET revisions returns newest revisions first."""
    job_id = await _insert_job(db_session)
    now = datetime.now(UTC)
    for rev_num in [1, 2, 3]:
        db_session.add(
            BlockRevision(
                id=str(uuid.uuid4()),
                job_id=job_id,
                block_id="test.sas:1",
                revision_number=rev_num,
                python_code=f"# rev {rev_num}",
                strategy="translate",
                confidence="high",
                uncertainty_notes=[],
                trigger="agent",
                created_at=now,
            )
        )
    await db_session.commit()

    resp = await client.get(f"/jobs/{job_id}/blocks/test.sas%3A1/revisions")
    assert resp.status_code == 200
    revisions = resp.json()["revisions"]
    assert len(revisions) == 3
    assert revisions[0]["revision_number"] == 3
    assert revisions[-1]["revision_number"] == 1


@pytest.mark.asyncio
async def test_get_block_revisions_job_not_found(client: AsyncClient) -> None:
    """GET revisions on a non-existent job returns 404."""
    resp = await client.get(f"/jobs/{uuid.uuid4()}/blocks/test.sas%3A1/revisions")
    assert resp.status_code == 404


# ── POST /jobs/{id}/blocks/{block_id}/revisions/{revision_id}/restore ────────


@pytest.mark.asyncio
async def test_restore_block_revision_happy_path(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Restoring a revision inserts a new restore revision and returns 200."""
    job_id = await _insert_job(db_session)
    now = datetime.now(UTC)
    rev_id = str(uuid.uuid4())
    db_session.add(
        BlockRevision(
            id=rev_id,
            job_id=job_id,
            block_id="test.sas:1",
            revision_number=1,
            python_code="# SAS: test.sas:1\nold = src.copy()\n",
            strategy="translate",
            confidence="medium",
            uncertainty_notes=["needs review"],
            trigger="agent",
            created_at=now,
        )
    )
    await db_session.commit()

    resp = await client.post(f"/jobs/{job_id}/blocks/test.sas%3A1/revisions/{rev_id}/restore")
    assert resp.status_code == 200
    body = resp.json()
    assert body["block_id"] == "test.sas:1"
    assert body["revision_number"] == 2
    assert body["confidence"] == "medium"


@pytest.mark.asyncio
async def test_restore_block_revision_not_found(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Restoring a non-existent revision returns 404."""
    job_id = await _insert_job(db_session)
    resp = await client.post(f"/jobs/{job_id}/blocks/test.sas%3A1/revisions/{uuid.uuid4()}/restore")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_restore_block_revision_accepted_job_returns_409(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Restoring a revision on an accepted job returns 409."""
    job_id = await _insert_job(db_session, accepted_at=datetime.now(UTC))
    resp = await client.post(f"/jobs/{job_id}/blocks/test.sas%3A1/revisions/{uuid.uuid4()}/restore")
    assert resp.status_code == 409
