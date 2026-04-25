"""Tests for /explain SSE routes and session CRUD endpoints."""

import json
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
import src.backend.api.routes.explain as explain_module
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Base, Job
from src.backend.db.session import get_async_session
from src.backend.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ── Fixtures ──────────────────────────────────────────────────────────────────


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


# ── SSE helpers ────────────────────────────────────────────────────────────────


async def _fake_stream(*args: object, **kwargs: object) -> AsyncGenerator[str, None]:
    """Fake answer_stream that yields two chunks."""
    yield "Hello "
    yield "world."


async def _fake_stream_empty(*args: object, **kwargs: object) -> AsyncGenerator[str, None]:
    """Fake answer_stream that yields nothing."""
    return
    yield  # make it an async generator


def _parse_sse(text: str) -> str:
    """Extract concatenated text chunks from SSE response body."""
    full = ""
    for line in text.splitlines():
        if line.startswith("data: ") and not line.startswith("data: [DONE]"):
            try:
                payload = json.loads(line[6:])
                if "chunk" in payload:
                    full += payload["chunk"]
            except json.JSONDecodeError:
                pass
    return full


def _sse_ends_with_done(text: str) -> bool:
    return "data: [DONE]" in text


# ── POST /explain (file-based SSE) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_explain_files_no_files(client: AsyncClient) -> None:
    """POST /explain returns SSE with answer chunks."""
    with patch.object(explain_module._explain_agent, "answer_stream", _fake_stream):
        resp = await client.post(
            "/explain",
            data={"question": "What does this code do?"},
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    answer = _parse_sse(resp.text)
    assert answer == "Hello world."
    assert _sse_ends_with_done(resp.text)


@pytest.mark.asyncio
async def test_explain_files_with_file(client: AsyncClient) -> None:
    """POST /explain with an uploaded file streams an answer."""
    with patch.object(explain_module._explain_agent, "answer_stream", _fake_stream):
        resp = await client.post(
            "/explain",
            data={"question": "What does this do?"},
            files=[("files", ("sample.sas", b"data work.out; set in; run;", "text/plain"))],
        )

    assert resp.status_code == 200
    assert _parse_sse(resp.text) == "Hello world."


@pytest.mark.asyncio
async def test_explain_files_bad_messages_json(client: AsyncClient) -> None:
    """POST /explain with invalid messages JSON returns HTTP 400."""
    resp = await client.post(
        "/explain",
        data={"question": "Q?", "messages": "not-json"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_explain_files_sse_done_sentinel(client: AsyncClient) -> None:
    """POST /explain SSE stream ends with [DONE] sentinel."""
    with patch.object(explain_module._explain_agent, "answer_stream", _fake_stream_empty):
        resp = await client.post("/explain", data={"question": "Q?"})

    assert resp.status_code == 200
    assert _sse_ends_with_done(resp.text)


# ── POST /explain/job (job-context SSE) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_explain_job_not_found(client: AsyncClient) -> None:
    """POST /explain/job with an unknown job_id returns HTTP 404."""
    with patch.object(explain_module._explain_agent, "answer_stream", _fake_stream):
        resp = await client.post(
            "/explain/job",
            json={"job_id": str(uuid.uuid4()), "question": "What does this job do?"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_explain_job_success(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /explain/job streams an answer when the job exists."""
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        status="done",
        input_hash="abc123",
        files={},
        migration_plan={"summary": "Test plan"},
        doc="Technical doc text",
        python_code="df = pd.read_csv('file.csv')",
    )
    db_session.add(job)
    await db_session.commit()

    with patch.object(explain_module._explain_agent, "answer_stream", _fake_stream):
        resp = await client.post(
            "/explain/job",
            json={"job_id": job_id, "question": "What does this job do?"},
        )

    assert resp.status_code == 200
    assert _parse_sse(resp.text) == "Hello world."


@pytest.mark.asyncio
async def test_explain_job_with_messages(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /explain/job passes prior conversation turns to the prompt."""
    job_id = str(uuid.uuid4())
    db_session.add(
        Job(
            id=job_id,
            status="done",
            input_hash="abc123",
            files={},
            migration_plan={"summary": "s"},
        )
    )
    await db_session.commit()

    captured: list[str] = []

    async def _capture_stream(
        prompt: str, audience: str = "tech", mode: str = "migration"
    ) -> AsyncGenerator[str, None]:
        captured.append(prompt)
        yield "Answer."

    with patch.object(explain_module._explain_agent, "answer_stream", _capture_stream):
        resp = await client.post(
            "/explain/job",
            json={
                "job_id": job_id,
                "question": "Follow-up question",
                "messages": [
                    {"role": "user", "content": "First question"},
                    {"role": "assistant", "content": "First answer"},
                ],
            },
        )

    assert resp.status_code == 200
    assert len(captured) == 1
    assert "First question" in captured[0]
    assert "First answer" in captured[0]


@pytest.mark.asyncio
async def test_explain_job_no_doc_still_answers(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /explain/job works when doc and python_code fields are absent."""
    job_id = str(uuid.uuid4())
    db_session.add(
        Job(id=job_id, status="done", input_hash="h", files={}, migration_plan={"summary": "s"})
    )
    await db_session.commit()

    with patch.object(explain_module._explain_agent, "answer_stream", _fake_stream):
        resp = await client.post(
            "/explain/job",
            json={"job_id": job_id, "question": "What does this do?"},
        )

    assert resp.status_code == 200
    assert _parse_sse(resp.text) == "Hello world."


# ── POST /explain/sessions ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_explain_session(client: AsyncClient) -> None:
    """POST /explain/sessions creates and returns a session."""
    resp = await client.post(
        "/explain/sessions",
        json={"mode": "migration", "audience": "tech"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "migration"
    assert body["audience"] == "tech"
    assert body["messages"] == []
    assert "session_id" in body


@pytest.mark.asyncio
async def test_create_explain_session_non_tech(client: AsyncClient) -> None:
    """POST /explain/sessions with non_tech audience stores the audience value."""
    resp = await client.post(
        "/explain/sessions",
        json={"mode": "sas_general", "audience": "non_tech"},
    )
    assert resp.status_code == 200
    assert resp.json()["audience"] == "non_tech"


# ── GET /explain/sessions ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_explain_sessions_empty(client: AsyncClient) -> None:
    """GET /explain/sessions returns empty list when no sessions exist."""
    resp = await client.get("/explain/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_explain_sessions_returns_created(client: AsyncClient) -> None:
    """GET /explain/sessions returns previously created sessions."""
    await client.post("/explain/sessions", json={"mode": "migration", "audience": "tech"})
    await client.post("/explain/sessions", json={"mode": "sas_general", "audience": "non_tech"})

    resp = await client.get("/explain/sessions")
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) == 2


# ── GET /explain/sessions/{id} ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_explain_session_not_found(client: AsyncClient) -> None:
    """GET /explain/sessions/{id} returns 404 for unknown session."""
    resp = await client.get(f"/explain/sessions/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_explain_session_found(client: AsyncClient) -> None:
    """GET /explain/sessions/{id} returns the session when it exists."""
    create_resp = await client.post(
        "/explain/sessions", json={"mode": "migration", "audience": "tech"}
    )
    session_id = create_resp.json()["session_id"]

    resp = await client.get(f"/explain/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["session_id"] == session_id


# ── GET /jobs?status= filter ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_jobs_status_filter(client: AsyncClient, db_session: AsyncSession) -> None:
    """GET /jobs?status= filters returned jobs by status."""
    for status in ("pending", "done", "done", "failed"):
        db_session.add(Job(id=str(uuid.uuid4()), status=status, input_hash="h", files={}))
    await db_session.commit()

    resp = await client.get("/jobs?status=done")
    assert resp.status_code == 200
    body = resp.json()
    assert all(j["status"] == "done" for j in body["jobs"])
    assert len(body["jobs"]) == 2


@pytest.mark.asyncio
async def test_list_jobs_status_filter_multiple(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /jobs?status=a,b returns jobs with status a or b."""
    for status in ("pending", "done", "failed"):
        db_session.add(Job(id=str(uuid.uuid4()), status=status, input_hash="h", files={}))
    await db_session.commit()

    resp = await client.get("/jobs?status=done,failed")
    assert resp.status_code == 200
    body = resp.json()
    statuses = {j["status"] for j in body["jobs"]}
    assert statuses == {"done", "failed"}


@pytest.mark.asyncio
async def test_list_jobs_no_filter(client: AsyncClient, db_session: AsyncSession) -> None:
    """GET /jobs without status filter returns all jobs."""
    for status in ("pending", "done"):
        db_session.add(Job(id=str(uuid.uuid4()), status=status, input_hash="h", files={}))
    await db_session.commit()

    resp = await client.get("/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["jobs"]) == 2


# ── _persist_messages coverage ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_persist_messages_direct() -> None:
    """_persist_messages appends user+assistant turns to the session's messages field."""
    import src.backend.api.routes.explain as explain_module
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from src.backend.db.models import Base, ExplainSession

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        session = ExplainSession(mode="migration", audience="tech", messages=[], context_files=[])
        db.add(session)
        await db.commit()
        session_id = session.id

    original = explain_module.AsyncSessionLocal  # type: ignore[attr-defined]
    explain_module.AsyncSessionLocal = factory  # type: ignore[attr-defined]
    try:
        await explain_module._persist_messages(session_id, "user q", "assistant a")
    finally:
        explain_module.AsyncSessionLocal = original  # type: ignore[attr-defined]

    async with factory() as db:
        result = await db.execute(
            __import__("sqlalchemy", fromlist=["select"])
            .select(ExplainSession)
            .where(ExplainSession.id == session_id)
        )
        refreshed = result.scalar_one()
    assert len(refreshed.messages) == 2
    assert refreshed.messages[0] == {"role": "user", "content": "user q"}
    assert refreshed.messages[1] == {"role": "assistant", "content": "assistant a"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_persist_messages_unknown_session_noop() -> None:
    """_persist_messages silently does nothing for a non-existent session_id."""
    import src.backend.api.routes.explain as explain_module
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from src.backend.db.models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    original = explain_module.AsyncSessionLocal  # type: ignore[attr-defined]
    explain_module.AsyncSessionLocal = factory  # type: ignore[attr-defined]
    try:
        # Should not raise
        await explain_module._persist_messages("nonexistent-id", "q", "a")
    finally:
        explain_module.AsyncSessionLocal = original  # type: ignore[attr-defined]
    await engine.dispose()


@pytest.mark.asyncio
async def test_explain_job_with_session_id_triggers_persist(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /explain/job with session_id schedules message persistence."""
    import src.backend.api.routes.explain as explain_module

    job_id = str(uuid.uuid4())
    db_session.add(Job(id=job_id, status="done", input_hash="h", files={}))
    await db_session.commit()

    session_resp = await client.post(
        "/explain/sessions", json={"mode": "migration", "audience": "tech"}
    )
    session_id = session_resp.json()["session_id"]

    with patch.object(explain_module._explain_agent, "answer_stream", _fake_stream):
        resp = await client.post(
            "/explain/job",
            json={"job_id": job_id, "question": "Q?", "session_id": session_id},
        )

    assert resp.status_code == 200
    assert _sse_ends_with_done(resp.text)
