"""Tests for POST /explain and POST /explain/job routes."""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

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
    """Create a fresh in-memory SQLite database for each test."""
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
    """Return an AsyncClient with the test database injected."""

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _mock_agent_run(answer: str) -> AsyncMock:
    """Return an async mock that simulates a pydantic-ai agent.run() result."""
    mock_result = AsyncMock()
    mock_result.output = answer
    mock_run = AsyncMock(return_value=mock_result)
    return mock_run


# ── POST /explain (file-based) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_explain_files_no_files(client: AsyncClient) -> None:
    """POST /explain with no files returns an answer from the LLM."""
    with patch("src.backend.api.routes.explain._get_explain_agent") as mock_get_agent:
        agent_mock = AsyncMock()
        agent_mock.run = _mock_agent_run("This code filters rows where value > 0.")
        mock_get_agent.return_value = agent_mock

        resp = await client.post(
            "/explain",
            data={"question": "What does this code do?"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "This code filters rows where value > 0."
    assert body["context_files"] == []


@pytest.mark.asyncio
async def test_explain_files_with_file(client: AsyncClient) -> None:
    """POST /explain with an uploaded file includes the filename in context_files."""
    with patch("src.backend.api.routes.explain._get_explain_agent") as mock_get_agent:
        agent_mock = AsyncMock()
        agent_mock.run = _mock_agent_run("It reads a CSV and filters it.")
        mock_get_agent.return_value = agent_mock

        resp = await client.post(
            "/explain",
            data={"question": "What does this do?"},
            files=[("files", ("sample.sas", b"data work.out; set in; run;", "text/plain"))],
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "sample.sas" in body["context_files"]


@pytest.mark.asyncio
async def test_explain_files_bad_messages_json(client: AsyncClient) -> None:
    """POST /explain with invalid messages JSON returns HTTP 400."""
    resp = await client.post(
        "/explain",
        data={"question": "Q?", "messages": "not-json"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_explain_files_llm_error_returns_500(client: AsyncClient) -> None:
    """POST /explain returns 500 when the LLM call raises."""
    with patch("src.backend.api.routes.explain._get_explain_agent") as mock_get_agent:
        agent_mock = AsyncMock()
        agent_mock.run = AsyncMock(side_effect=RuntimeError("LLM down"))
        mock_get_agent.return_value = agent_mock

        resp = await client.post("/explain", data={"question": "Q?"})

    assert resp.status_code == 500


# ── POST /explain/job (job-context) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_explain_job_not_found(client: AsyncClient) -> None:
    """POST /explain/job with an unknown job_id returns HTTP 404."""
    with patch("src.backend.api.routes.explain._get_explain_agent"):
        resp = await client.post(
            "/explain/job",
            json={
                "job_id": str(uuid.uuid4()),
                "question": "What does this job do?",
            },
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_explain_job_success(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /explain/job returns an answer when the job exists."""
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        status="done",
        input_hash="abc123",
        files={},
        migration_plan={"summary": "Test plan"},
        doc="Technical doc text",
        python_code="df = pd.read_csv('file.csv')",
        report={"non_technical_doc": "Business summary text"},
    )
    db_session.add(job)
    await db_session.commit()

    with patch("src.backend.api.routes.explain._get_explain_agent") as mock_get_agent:
        agent_mock = AsyncMock()
        agent_mock.run = _mock_agent_run("This job reads a CSV and filters it.")
        mock_get_agent.return_value = agent_mock

        resp = await client.post(
            "/explain/job",
            json={
                "job_id": job_id,
                "question": "What does this job do?",
                "context_fields": ["plan", "doc", "python_code"],
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "This job reads a CSV and filters it."
    assert body["job_id"] == job_id


@pytest.mark.asyncio
async def test_explain_job_with_messages(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /explain/job passes prior conversation turns to the LLM prompt."""
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id, status="done", input_hash="abc123", files={}, migration_plan={"summary": "s"}
    )
    db_session.add(job)
    await db_session.commit()

    captured_prompts: list[str] = []

    async def capture_run(prompt: str) -> AsyncMock:
        captured_prompts.append(prompt)
        result = AsyncMock()
        result.output = "Follow-up answer."
        return result

    with patch("src.backend.api.routes.explain._get_explain_agent") as mock_get_agent:
        agent_mock = AsyncMock()
        agent_mock.run = capture_run
        mock_get_agent.return_value = agent_mock

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
    assert "First question" in captured_prompts[0]
    assert "First answer" in captured_prompts[0]


@pytest.mark.asyncio
async def test_explain_job_llm_error_returns_500(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /explain/job returns 500 when the LLM call raises."""
    job_id = str(uuid.uuid4())
    db_session.add(Job(id=job_id, status="done", input_hash="h", files={}))
    await db_session.commit()

    with patch("src.backend.api.routes.explain._get_explain_agent") as mock_get_agent:
        agent_mock = AsyncMock()
        agent_mock.run = AsyncMock(side_effect=RuntimeError("LLM down"))
        mock_get_agent.return_value = agent_mock

        resp = await client.post(
            "/explain/job",
            json={"job_id": job_id, "question": "Q?"},
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_explain_job_no_doc_still_answers(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /explain/job works when doc and report fields are absent."""
    job_id = str(uuid.uuid4())
    db_session.add(
        Job(id=job_id, status="done", input_hash="h", files={}, migration_plan={"summary": "s"})
    )
    await db_session.commit()

    with patch("src.backend.api.routes.explain._get_explain_agent") as mock_get_agent:
        agent_mock = AsyncMock()
        agent_mock.run = _mock_agent_run("Answer without doc.")
        mock_get_agent.return_value = agent_mock

        resp = await client.post(
            "/explain/job",
            json={"job_id": job_id, "question": "What does this do?"},
        )

    assert resp.status_code == 200
    assert resp.json()["answer"] == "Answer without doc."


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
