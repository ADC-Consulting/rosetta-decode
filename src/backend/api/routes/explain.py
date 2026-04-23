"""Explain endpoints — interactive Q&A over uploaded files or a job context.

Provides SSE-streaming routes:
- POST /explain         — file-based Q&A (multipart, SSE)
- POST /explain/job     — job-context Q&A (JSON body, SSE)

And session persistence CRUD:
- POST   /explain/sessions
- GET    /explain/sessions
- GET    /explain/sessions/{session_id}
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.backend.api.schemas import (
    CreateExplainSessionRequest,
    ExplainJobRequest,
    ExplainMessage,
    ExplainResponse,
    ExplainSessionResponse,
)
from src.backend.db.models import ExplainSession, Job
from src.backend.db.session import get_async_session
from src.worker.engine.chatbot import ExplainAgent

logger = logging.getLogger(__name__)
router = APIRouter()

_explain_agent = ExplainAgent()
_background_tasks: set[asyncio.Task[Any]] = set()  # prevent GC of fire-and-forget tasks

# ── Session helpers ────────────────────────────────────────────────────────────


def _session_to_response(s: ExplainSession) -> ExplainSessionResponse:
    """Convert an ORM ExplainSession to its response schema.

    Args:
        s: The ORM model instance.

    Returns:
        ExplainSessionResponse populated from the model.
    """
    return ExplainSessionResponse(
        session_id=s.id,
        messages=[ExplainMessage(**m) for m in (s.messages or [])],
        mode=s.mode,
        audience=s.audience,
        created_at=s.created_at,
    )


# ── Session CRUD ───────────────────────────────────────────────────────────────


@router.post("/explain/sessions", response_model=ExplainSessionResponse)
async def create_explain_session(
    req: CreateExplainSessionRequest,
    db: AsyncSession = Depends(get_async_session),
) -> ExplainSessionResponse:
    """Create a new explain session.

    Args:
        req: Session creation parameters.
        db: Injected async database session.

    Returns:
        The newly created ExplainSessionResponse.
    """
    session = ExplainSession(
        mode=req.mode,
        job_id=req.job_id,
        audience=req.audience,
        messages=[],
        context_files=[],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _session_to_response(session)


@router.get("/explain/sessions", response_model=list[ExplainSessionResponse])
async def list_explain_sessions(
    db: AsyncSession = Depends(get_async_session),
) -> list[ExplainSessionResponse]:
    """List the 20 most-recent explain sessions.

    Args:
        db: Injected async database session.

    Returns:
        List of ExplainSessionResponse ordered by created_at descending.
    """
    result = await db.execute(
        select(ExplainSession).order_by(ExplainSession.created_at.desc()).limit(20)
    )
    sessions = result.scalars().all()
    return [_session_to_response(s) for s in sessions]


@router.get("/explain/sessions/{session_id}", response_model=ExplainSessionResponse)
async def get_explain_session(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> ExplainSessionResponse:
    """Retrieve a single explain session by ID.

    Args:
        session_id: The session UUID.
        db: Injected async database session.

    Returns:
        ExplainSessionResponse for the requested session.

    Raises:
        HTTPException: 404 if the session does not exist.
    """
    result = await db.execute(select(ExplainSession).where(ExplainSession.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_to_response(session)


# ── SSE helper ─────────────────────────────────────────────────────────────────


async def _sse_stream(
    prompt: str,
    audience: str,
    session_id: str | None,
    user_message: str,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Generate SSE events from the ExplainAgent and optionally persist messages.

    Args:
        prompt: Full prompt to send to the LLM.
        audience: "tech" or "non_tech".
        session_id: Optional session to persist messages into.
        user_message: Raw user question text (stored in history).
        db: Async database session for persistence.

    Yields:
        SSE-formatted data strings.
    """
    full_response = ""
    try:
        async for chunk in _explain_agent.answer_stream(prompt, audience=audience):
            full_response += chunk
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        yield f"data: {json.dumps({'tokens_used': None})}\n\n"
        yield "data: [DONE]\n\n"
    finally:
        if session_id:
            task = asyncio.create_task(
                _persist_messages(session_id, user_message, full_response, db)
            )
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)


async def _persist_messages(
    session_id: str,
    user_content: str,
    assistant_content: str,
    db: AsyncSession,
) -> None:
    """Append user+assistant messages to an explain session.

    Args:
        session_id: Target session UUID.
        user_content: The user's question.
        assistant_content: The assistant's full response.
        db: Async database session.
    """
    try:
        result = await db.execute(select(ExplainSession).where(ExplainSession.id == session_id))
        session = result.scalar_one_or_none()
        if session is None:
            return
        msgs: list[dict[str, str]] = list(session.messages or [])
        msgs.append({"role": "user", "content": user_content})
        msgs.append({"role": "assistant", "content": assistant_content})
        session.messages = msgs
        session.updated_at = datetime.now(UTC)
        await db.commit()
    except Exception:
        logger.exception("Failed to persist explain messages for session %s", session_id)


# ── File-based Q&A (SSE) ───────────────────────────────────────────────────────


@router.post("/explain")
async def explain_files(
    question: str = Form(...),
    messages: str = Form("[]"),
    audience: str = Form("tech"),
    session_id: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_async_session),
) -> StreamingResponse:
    """Answer a question about uploaded files using SSE streaming.

    Args:
        question: The user's question (form field).
        messages: JSON-encoded list of prior conversation turns (form field).
        audience: "tech" or "non_tech" (form field).
        session_id: Optional session UUID for persistence (form field).
        files: Uploaded files to use as context.
        db: Injected async database session.

    Returns:
        StreamingResponse with SSE events.

    Raises:
        HTTPException: 400 if messages JSON is malformed.
    """
    try:
        history: list[dict[str, Any]] = json.loads(messages)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid messages JSON: {exc}") from exc

    context_parts: list[str] = []
    for upload in files:
        raw = await upload.read()
        text = raw.decode("utf-8", errors="replace")
        context_parts.append(f"=== File: {upload.filename} ===\n{text}")

    context = "\n\n".join(context_parts)
    history_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history[-10:])
    prompt_parts: list[str] = []
    if context:
        prompt_parts.append(f"Context:\n{context}")
    if history_text:
        prompt_parts.append(f"Conversation history:\n{history_text}")
    prompt_parts.append(f"USER: {question}")
    prompt = "\n\n".join(prompt_parts)

    return StreamingResponse(
        _sse_stream(prompt, audience, session_id, question, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Job-based Q&A (SSE) ────────────────────────────────────────────────────────


class _ExplainJobSSERequest(ExplainJobRequest):
    """Extended ExplainJobRequest with SSE session fields."""

    session_id: str | None = None
    audience: str = "tech"


@router.post("/explain/job")
async def explain_job(
    req: _ExplainJobSSERequest,
    db: AsyncSession = Depends(get_async_session),
) -> StreamingResponse:
    """Answer a question about a migration job using SSE streaming.

    Args:
        req: JSON body with job_id, question, optional messages, session_id, audience.
        db: Injected async database session.

    Returns:
        StreamingResponse with SSE events.

    Raises:
        HTTPException: 404 if the job does not exist.
    """
    result = await db.execute(select(Job).where(Job.id == str(req.job_id)))
    job: Job | None = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {req.job_id} not found")

    parts: list[str] = []
    if job.migration_plan:
        parts.append(f"Migration plan:\n{json.dumps(job.migration_plan, indent=2)}")
    if job.python_code:
        parts.append(f"Generated Python:\n```python\n{job.python_code}\n```")
    if job.doc:
        parts.append(f"Documentation:\n{job.doc}")
    if job.lineage:
        parts.append(f"Lineage:\n{json.dumps(job.lineage, indent=2)}")

    context = "\n\n".join(parts)
    prior = [{"role": m.role, "content": m.content} for m in req.messages]
    history_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in prior[-10:])
    prompt_parts: list[str] = []
    if context:
        prompt_parts.append(f"Context:\n{context}")
    if history_text:
        prompt_parts.append(f"Conversation history:\n{history_text}")
    prompt_parts.append(f"USER: {req.question}")
    prompt = "\n\n".join(prompt_parts)

    return StreamingResponse(
        _sse_stream(prompt, req.audience, req.session_id, req.question, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Legacy non-streaming compat ────────────────────────────────────────────────


@router.post("/explain/legacy", response_model=ExplainResponse)
async def explain_files_legacy(
    question: str = Form(...),
    messages: str = Form(default="[]"),
    files: list[UploadFile] = File(default=[]),
) -> ExplainResponse:
    """Non-streaming file-based Q&A kept for backward compatibility.

    Args:
        question: The user's question (form field).
        messages: JSON-encoded prior conversation turns (form field).
        files: Uploaded files to use as context.

    Returns:
        ExplainResponse with the full LLM answer.

    Raises:
        HTTPException: 400 if messages JSON is malformed.
    """
    try:
        prior: list[dict[str, Any]] = json.loads(messages)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid messages JSON: {exc}") from exc

    context_parts: list[str] = []
    for f in files:
        raw = await f.read()
        context_parts.append(f"=== File: {f.filename} ===\n{raw.decode('utf-8', errors='replace')}")
    context = "\n\n".join(context_parts)
    history_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in prior[-10:])
    prompt_parts: list[str] = []
    if context:
        prompt_parts.append(f"Context:\n{context}")
    if history_text:
        prompt_parts.append(f"Conversation history:\n{history_text}")
    prompt_parts.append(f"USER: {question}")
    prompt = "\n\n".join(prompt_parts)

    chunks: list[str] = []
    async for chunk in _explain_agent.answer_stream(prompt, audience="tech"):
        chunks.append(chunk)
    answer = "".join(chunks)
    return ExplainResponse(answer=answer, context_files=[f.filename or "" for f in files])
