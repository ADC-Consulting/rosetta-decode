"""Explain endpoints — interactive Q&A over uploaded files or a job context.

Provides two POST routes:
- POST /explain  — file-based Q&A (multipart)
- POST /explain/job — job-context Q&A (JSON body)
"""

import json
import logging
import textwrap
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.azure import AzureProvider
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.backend.api.schemas import ExplainJobRequest, ExplainResponse
from src.backend.db.models import Job
from src.backend.db.session import get_async_session
from src.worker.core.config import worker_settings

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Agent factory ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = textwrap.dedent("""\
    # agent: ExplainAgent

    You are an expert assistant helping users understand a SAS-to-Python migration.
    You will be given context extracted from the migration (plan, documentation,
    generated Python code, or raw source files) and must answer the user's question
    clearly and concisely.

    Rules:
    - Answer only what is asked; do not repeat the full context back.
    - If the context does not contain enough information to answer, say so honestly.
    - Use plain language unless the user asks for technical detail.
    - If code is relevant, include short, focused snippets.
""")

_AGENT: "Agent[str] | None" = None


def _make_explain_agent() -> "Agent[str]":
    """Instantiate the pydantic-ai explain agent.

    Returns:
        A pydantic-ai Agent configured for free-form string output.
    """
    model_obj: OpenAIChatModel | KnownModelName

    if worker_settings.tensorzero_gateway_url:
        raw = worker_settings.llm_model
        base_name = raw.split(":", 1)[-1] if ":" in raw else raw
        tz_model_name = f"tensorzero::model_name::{base_name}"
        tz_provider = OpenAIProvider(
            base_url=worker_settings.tensorzero_gateway_url,
            api_key="tensorzero",
        )
        model_obj = OpenAIChatModel(model_name=tz_model_name, provider=tz_provider)
    elif worker_settings.azure_openai_endpoint:
        az_provider = AzureProvider(
            azure_endpoint=worker_settings.azure_openai_endpoint,
            api_key=worker_settings.azure_openai_api_key,
            api_version=worker_settings.openai_api_version,
        )
        raw = worker_settings.llm_model
        deployment = raw.split(":", 1)[-1] if ":" in raw else raw
        model_obj = OpenAIChatModel(model_name=deployment, provider=az_provider)
    else:
        model_obj = worker_settings.llm_model  # type: ignore[assignment]

    return Agent(
        model=model_obj,
        output_type=str,
        system_prompt=_SYSTEM_PROMPT,
    )


def _get_explain_agent() -> "Agent[str]":
    """Return the singleton ExplainAgent, creating it on first call.

    Returns:
        The shared Agent[str] instance.
    """
    global _AGENT
    if _AGENT is None:
        _AGENT = _make_explain_agent()
    return _AGENT


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_file_prompt(
    question: str,
    file_contents: list[tuple[str, str]],
    prior_messages: list[dict[str, Any]],
) -> str:
    """Build a prompt string that includes uploaded file contents and conversation history.

    Args:
        question: The user's current question.
        file_contents: List of (filename, content) tuples.
        prior_messages: Prior conversation turns as list of {role, content} dicts.

    Returns:
        Formatted prompt string.
    """
    parts: list[str] = []

    if file_contents:
        parts.append("## Uploaded files\n")
        for filename, content in file_contents:
            parts.append(f"### {filename}\n```\n{content[:4000]}\n```\n")

    if prior_messages:
        parts.append("## Conversation history\n")
        for msg in prior_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append(f"**{role}**: {content}\n")

    parts.append(f"## Question\n{question}")
    return "\n".join(parts)


def _build_job_prompt(
    question: str,
    job: Job,
    context_fields: "Sequence[str]",
    prior_messages: list[dict[str, Any]],
) -> str:
    """Build a prompt string from job context fields and conversation history.

    Args:
        question: The user's current question.
        job: The Job ORM object.
        context_fields: Which context sections to include.
        prior_messages: Prior conversation turns as list of {role, content} dicts.

    Returns:
        Formatted prompt string.
    """
    parts: list[str] = []

    if job.migration_plan:
        summary = json.dumps(job.migration_plan, indent=2)
        parts.append(f"## Migration plan\n```json\n{summary[:4000]}\n```\n")

    if "doc" in context_fields and job.doc:
        parts.append(f"## Technical documentation\n{job.doc[:4000]}\n")

    if "doc" in context_fields and job.report and job.report.get("non_technical_doc"):
        parts.append(f"## Business summary\n{job.report['non_technical_doc'][:2000]}\n")

    if "python_code" in context_fields and job.python_code:
        parts.append(f"## Generated Python code\n```python\n{job.python_code[:6000]}\n```\n")

    if prior_messages:
        parts.append("## Conversation history\n")
        for msg in prior_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append(f"**{role}**: {content}\n")

    parts.append(f"## Question\n{question}")
    return "\n".join(parts)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/explain", response_model=ExplainResponse)
async def explain_files(
    question: str = Form(...),
    messages: str = Form(default="[]"),
    files: list[UploadFile] = File(default=[]),
) -> ExplainResponse:
    """Answer a question about uploaded files using the LLM.

    Args:
        question: The user's question (form field).
        messages: JSON-encoded list of prior conversation turns (form field).
        files: Uploaded files to use as context.

    Returns:
        ExplainResponse with the LLM answer and list of context filenames.

    Raises:
        HTTPException: 400 if messages JSON is malformed; 500 on LLM failure.
    """
    try:
        prior: list[dict[str, Any]] = json.loads(messages)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid messages JSON: {exc}") from exc

    file_contents: list[tuple[str, str]] = []
    for f in files:
        raw = await f.read()
        file_contents.append((f.filename or "unknown", raw.decode("utf-8", errors="replace")))

    prompt = _build_file_prompt(question, file_contents, prior)

    agent = _get_explain_agent()
    try:
        result = await agent.run(prompt)
    except Exception as exc:
        logger.exception("ExplainAgent LLM call failed")
        raise HTTPException(status_code=500, detail=f"LLM call failed: {exc}") from exc

    answer: str = str(result.output)
    return ExplainResponse(
        answer=answer,
        context_files=[f.filename or "" for f in files],
    )


@router.post("/explain/job", response_model=ExplainResponse)
async def explain_job(
    req: ExplainJobRequest,
    session: AsyncSession = Depends(get_async_session),
) -> ExplainResponse:
    """Answer a question about a specific migration job using its stored context.

    Args:
        req: JSON body with job_id, question, optional messages, and context_fields.
        session: Injected async database session.

    Returns:
        ExplainResponse with the LLM answer and the resolved job_id.

    Raises:
        HTTPException: 404 if job not found; 500 on LLM failure.
    """
    result = await session.execute(select(Job).where(Job.id == str(req.job_id)))
    job: Job | None = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {req.job_id} not found")

    prior: list[dict[str, Any]] = [{"role": m.role, "content": m.content} for m in req.messages]

    prompt = _build_job_prompt(req.question, job, req.context_fields, prior)

    agent = _get_explain_agent()
    try:
        result_llm = await agent.run(prompt)
    except Exception as exc:
        logger.exception("ExplainAgent LLM call failed for job %s", req.job_id)
        raise HTTPException(status_code=500, detail=f"LLM call failed: {exc}") from exc

    answer: str = str(result_llm.output)
    return ExplainResponse(answer=answer, job_id=req.job_id)
