"""GET /jobs/{id} — retrieve job status, audit record, and downloadable artefacts."""

import asyncio
import difflib
import io
import json
import logging
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.backend.api.schemas import (
    AcceptJobRequest,
    AuditResponse,
    BlockRefineRequest,
    BlockRefineResponse,
    BlockRevisionListResponse,
    BlockRevisionResponse,
    ChangelogEntry,
    JobChangelogResponse,
    JobDocResponse,
    JobHistoryEntry,
    JobHistoryResponse,
    JobLineageResponse,
    JobListResponse,
    JobPlanResponse,
    JobSourcesResponse,
    JobStatusResponse,
    JobSummary,
    JobVersionDetail,
    JobVersionSummary,
    PatchPlanRequest,
    RefineRequest,
    RefineResponse,
    SaveVersionRequest,
    SaveVersionResponse,
    TrustReportBlock,
    TrustReportFile,
    TrustReportResponse,
    UpdatePythonCodeRequest,
)
from src.backend.db.models import BlockRevision, Job, JobVersion
from src.backend.db.session import get_async_session
from src.worker.compute.local import LocalBackend
from src.worker.engine.agents.data_step import DataStepAgent
from src.worker.engine.agents.generic_proc import GenericProcAgent
from src.worker.engine.agents.proc import ProcAgent
from src.worker.engine.models import JobContext, SASBlock
from src.worker.engine.parser import SASParser
from src.worker.engine.router import TranslationRouter
from src.worker.engine.stub_generator import StubGenerator
from src.worker.validation.reconciliation import ReconciliationService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    session: AsyncSession = Depends(get_async_session),
) -> JobListResponse:
    """Return a summary list of all migration jobs, newest first.

    Args:
        session: Injected async database session.

    Returns:
        JobListResponse containing a list of JobSummary entries.
    """
    result = await session.execute(select(Job).order_by(Job.created_at.desc()))
    jobs = result.scalars().all()
    return JobListResponse(
        jobs=[
            JobSummary(
                job_id=uuid.UUID(j.id),
                status=j.status,
                created_at=j.created_at,
                updated_at=j.updated_at,
                error=j.error,
                name=j.name,
                file_count=len(j.files or {}),
            )
            for j in jobs
        ]
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> JobStatusResponse:
    """Return the current status and available output for a job.

    Args:
        job_id: UUID of the migration job.
        session: Injected async database session.

    Returns:
        JobStatusResponse with status and any completed output.

    Raises:
        HTTPException: 404 if the job does not exist.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    return JobStatusResponse(
        job_id=uuid.UUID(job.id),
        status=job.status,
        python_code=job.python_code,
        report=job.report,
        error=job.error,
        name=job.name,
        generated_files=job.generated_files,
        user_overrides=job.user_overrides,
        accepted_at=job.accepted_at,
        parent_job_id=job.parent_job_id,
        trigger=job.trigger,
        skip_llm=job.skip_llm,
    )


@router.get("/jobs/{job_id}/sources", response_model=JobSourcesResponse)
async def get_job_sources(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> JobSourcesResponse:
    """Return raw source files for a job, excluding internal sentinel keys.

    Args:
        job_id: UUID of the migration job.
        session: Injected async database session.

    Returns:
        JobSourcesResponse mapping filename to source content.

    Raises:
        HTTPException: 404 if the job does not exist.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    sources = {k: v for k, v in (job.files or {}).items() if not k.startswith("__")}
    return JobSourcesResponse(job_id=job_id, sources=sources)


@router.get("/jobs/{job_id}/audit", response_model=AuditResponse)
async def get_job_audit(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> AuditResponse:
    """Return an immutable audit record for a job.

    Args:
        job_id: UUID of the migration job.
        session: Injected async database session.

    Returns:
        AuditResponse with provenance and reconciliation report.

    Raises:
        HTTPException: 404 if the job does not exist.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return AuditResponse(
        job_id=uuid.UUID(job.id),
        input_hash=job.input_hash,
        llm_model=job.llm_model,
        created_at=job.created_at,
        updated_at=job.updated_at,
        report=job.report,
    )


@router.get("/jobs/{job_id}/download")
async def download_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> StreamingResponse:
    """Return a zip archive of all migration artefacts for a completed job.

    The zip contains:
    - ``pipeline.py`` — generated Python pipeline
    - ``reconciliation_report.json`` — structured reconciliation results
    - ``audit.json`` — provenance metadata

    Args:
        job_id: UUID of the migration job.
        session: Injected async database session.

    Returns:
        StreamingResponse with a zip file named ``rosetta-{job_id}.zip``.

    Raises:
        HTTPException: 404 if the job does not exist, 409 if not yet complete.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.status not in ("proposed", "accepted", "done"):
        raise HTTPException(status_code=409, detail="Job is not yet complete.")

    audit_payload = {
        "job_id": str(job_id),
        "input_hash": job.input_hash,
        "llm_model": job.llm_model,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("pipeline.py", job.python_code or "")
        zf.writestr("reconciliation_report.json", json.dumps(job.report or {}))
        zf.writestr("audit.json", json.dumps(audit_payload))
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=rosetta-{job_id}.zip"},
    )


@router.get("/jobs/{job_id}/lineage", response_model=None)
async def get_job_lineage(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> JSONResponse | JobLineageResponse:
    """Return the data-lineage graph for a job.

    Args:
        job_id: UUID of the migration job.
        session: Injected async database session.

    Returns:
        202 empty JSON if lineage has not been computed yet, or 200 with
        JobLineageResponse once the worker has stored lineage data.

    Raises:
        HTTPException: 404 if the job does not exist.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.lineage is None:
        return JSONResponse(status_code=202, content={})
    lineage: dict[str, Any] = job.lineage
    return JobLineageResponse(
        job_id=job_id,
        nodes=lineage.get("nodes", []),
        edges=lineage.get("edges", []),
        column_flows=lineage.get("column_flows", []),
        macro_usages=lineage.get("macro_usages", []),
        cross_file_edges=lineage.get("cross_file_edges", []),
        dataset_summaries=lineage.get("dataset_summaries", {}),
        file_nodes=lineage.get("file_nodes", []),
        file_edges=lineage.get("file_edges", []),
        pipeline_steps=lineage.get("pipeline_steps", []),
        block_status=lineage.get("block_status", []),
        log_links=lineage.get("log_links", []),
    )


@router.get("/jobs/{job_id}/doc", response_model=JobDocResponse)
async def get_job_doc(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> JobDocResponse:
    """Return the LLM-generated documentation for a job.

    Args:
        job_id: UUID of the migration job.
        session: Injected async database session.

    Returns:
        JobDocResponse with doc string (null if not yet generated).

    Raises:
        HTTPException: 404 if the job does not exist.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return JobDocResponse(job_id=job_id, doc=job.doc)


@router.get("/jobs/{job_id}/plan", response_model=None)
async def get_job_plan(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> JSONResponse | JobPlanResponse:
    """Return the LLM-generated migration plan for a job.

    Args:
        job_id: UUID of the migration job.
        session: Injected async database session.

    Returns:
        202 with current status if the job is not yet done, or 200 with
        JobPlanResponse once the worker has stored the migration plan.

    Raises:
        HTTPException: 404 if the job does not exist or plan is unavailable.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.status not in ("proposed", "accepted", "done"):
        return JSONResponse(status_code=202, content={"status": job.status})
    if job.migration_plan is None:
        raise HTTPException(status_code=404, detail="Migration plan not available.")
    return JobPlanResponse(**job.migration_plan, job_id=job.id)


_REVIEW_STATUSES = frozenset({"proposed", "accepted"})


@router.post("/jobs/{job_id}/accept", response_model=JobStatusResponse)
async def accept_job(
    job_id: uuid.UUID,
    request: AcceptJobRequest,
    session: AsyncSession = Depends(get_async_session),
) -> JobStatusResponse:
    """Accept a proposed migration, recording the reviewer decision.

    Sets status to ``accepted``, stamps ``accepted_at``, and persists any
    acceptance note into ``user_overrides["acceptance_note"]``.

    Args:
        job_id: UUID of the migration job.
        request: Optional acceptance note.
        session: Injected async database session.

    Returns:
        Updated JobStatusResponse with status=accepted.

    Raises:
        HTTPException: 404 if the job does not exist, 409 if not in a reviewable state.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.status not in _REVIEW_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Job cannot be accepted in status '{job.status}'.",
        )

    accepted_at = datetime.now(UTC)
    overrides: dict[str, Any] = dict(job.user_overrides or {})
    if request.notes is not None:
        overrides["acceptance_note"] = request.notes

    await session.execute(
        update(Job)
        .where(Job.id == str(job_id))
        .values(status="accepted", accepted_at=accepted_at, user_overrides=overrides)
    )
    await session.commit()

    result2 = await session.execute(select(Job).where(Job.id == str(job_id)))
    updated = result2.scalar_one()
    return JobStatusResponse(
        job_id=uuid.UUID(updated.id),
        status=updated.status,
        python_code=updated.python_code,
        report=updated.report,
        error=updated.error,
        name=updated.name,
        generated_files=updated.generated_files,
        user_overrides=updated.user_overrides,
        accepted_at=updated.accepted_at,
    )


@router.patch("/jobs/{job_id}/plan", response_model=JobStatusResponse)
async def patch_job_plan(
    job_id: uuid.UUID,
    request: PatchPlanRequest,
    session: AsyncSession = Depends(get_async_session),
) -> JobStatusResponse:
    """Persist reviewer per-block overrides for a proposed or accepted job.

    Merges ``request.block_overrides`` into ``user_overrides["block_overrides"]``,
    replacing entries with the same ``block_id`` and appending new ones.

    Args:
        job_id: UUID of the migration job.
        request: List of per-block overrides to merge.
        session: Injected async database session.

    Returns:
        Updated JobStatusResponse reflecting the merged overrides.

    Raises:
        HTTPException: 404 if the job does not exist, 409 if not in a reviewable state.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.status not in _REVIEW_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Job plan cannot be patched in status '{job.status}'.",
        )

    overrides: dict[str, Any] = dict(job.user_overrides or {})
    existing: list[dict[str, Any]] = list(overrides.get("block_overrides", []))

    existing_by_id: dict[str, int] = {b["block_id"]: i for i, b in enumerate(existing)}
    for override in request.block_overrides:
        entry = override.model_dump()
        if override.block_id in existing_by_id:
            existing[existing_by_id[override.block_id]] = entry
        else:
            existing.append(entry)
            existing_by_id[override.block_id] = len(existing) - 1

    overrides["block_overrides"] = existing

    await session.execute(update(Job).where(Job.id == str(job_id)).values(user_overrides=overrides))
    await session.commit()

    result2 = await session.execute(select(Job).where(Job.id == str(job_id)))
    updated = result2.scalar_one()
    return JobStatusResponse(
        job_id=uuid.UUID(updated.id),
        status=updated.status,
        python_code=updated.python_code,
        report=updated.report,
        error=updated.error,
        name=updated.name,
        generated_files=updated.generated_files,
        user_overrides=updated.user_overrides,
        accepted_at=updated.accepted_at,
    )


@router.put("/jobs/{job_id}/python_code", response_model=JobStatusResponse)
async def update_python_code(
    job_id: uuid.UUID,
    request: UpdatePythonCodeRequest,
    session: AsyncSession = Depends(get_async_session),
) -> JobStatusResponse:
    """Replace the generated Python code and re-queue reconciliation.

    Sets ``skip_llm=True`` so the worker skips LLM translation and runs only
    reconciliation against the new code.

    Args:
        job_id: UUID of the migration job.
        request: New Python code to persist.
        session: Injected async database session.

    Returns:
        Updated JobStatusResponse.

    Raises:
        HTTPException: 404 if not found, 409 if the job is currently running.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.status == "running":
        raise HTTPException(status_code=409, detail="Cannot update code while job is running.")

    await session.execute(
        update(Job)
        .where(Job.id == str(job_id))
        .values(
            python_code=request.python_code,
            status="queued",
            skip_llm=True,
            trigger="human-rereconcile",
            report=None,
        )
    )
    await session.commit()

    result2 = await session.execute(select(Job).where(Job.id == str(job_id)))
    updated = result2.scalar_one()
    return JobStatusResponse(
        job_id=uuid.UUID(updated.id),
        status=updated.status,
        python_code=updated.python_code,
        report=updated.report,
        error=updated.error,
        name=updated.name,
        generated_files=updated.generated_files,
        user_overrides=updated.user_overrides,
        accepted_at=updated.accepted_at,
        parent_job_id=updated.parent_job_id,
        trigger=updated.trigger,
        skip_llm=updated.skip_llm,
    )


@router.post("/jobs/{job_id}/refine", response_model=RefineResponse)
async def refine_job(
    job_id: uuid.UUID,
    request: RefineRequest,
    session: AsyncSession = Depends(get_async_session),
) -> RefineResponse:
    """Create a child job that re-runs the full pipeline with a reviewer hint.

    The parent job's files are copied into the child with a ``__refine_context__``
    sentinel that carries the prior Python code and the optional hint string so the
    worker can inject them into the LLM translation prompt.

    Args:
        job_id: UUID of the parent migration job.
        request: Optional free-text hint for the LLM.
        session: Injected async database session.

    Returns:
        RefineResponse with the new child job ID.

    Raises:
        HTTPException: 404 if the parent job does not exist.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    parent = result.scalar_one_or_none()
    if parent is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if parent.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Job has been accepted and cannot be refined.")

    child_files: dict[str, Any] = dict(parent.files or {})
    child_files["__refine_context__"] = json.dumps(
        {
            "prior_python_code": parent.python_code or "",
            "hint": request.hint or "",
        }
    )

    new_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    new_job = Job(
        id=new_id,
        status="queued",
        input_hash=parent.input_hash,
        name=parent.name,
        files=child_files,
        parent_job_id=str(job_id),
        trigger="human-refine",
        skip_llm=False,
        created_at=now,
        updated_at=now,
    )
    session.add(new_job)
    await session.commit()
    return RefineResponse(job_id=new_id)


@router.get("/jobs/{job_id}/history", response_model=JobHistoryResponse)
async def get_job_history(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> JobHistoryResponse:
    """Return the full version chain for a job, from root ancestor to latest leaf.

    Walks up via ``parent_job_id`` to find the root, then collects all jobs that
    share that ancestry.

    Args:
        job_id: UUID of any job in the chain.
        session: Injected async database session.

    Returns:
        JobHistoryResponse with entries sorted oldest-first.

    Raises:
        HTTPException: 404 if the job does not exist.
    """
    # Step 1 — load the starting job
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    start_job = result.scalar_one_or_none()
    if start_job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    # Step 2 — walk up to root, collecting IDs in order (oldest first once reversed)
    chain: list[Job] = [start_job]
    visited: set[str] = {start_job.id}
    current = start_job
    while current.parent_job_id is not None and current.parent_job_id not in visited:
        visited.add(current.parent_job_id)
        pr = await session.execute(select(Job).where(Job.id == current.parent_job_id))
        parent_job = pr.scalar_one_or_none()
        if parent_job is None:
            break
        chain.append(parent_job)
        current = parent_job

    chain.reverse()  # oldest first

    # Step 3 — walk down: find children of any job in the chain
    all_ids: set[str] = {j.id for j in chain}
    frontier: set[str] = all_ids.copy()
    while frontier:
        children_result = await session.execute(
            select(Job).where(Job.parent_job_id.in_(list(frontier)))
        )
        children = children_result.scalars().all()
        new_ids = {c.id for c in children if c.id not in all_ids}
        for c in children:
            if c.id not in all_ids:
                chain.append(c)
                all_ids.add(c.id)
        frontier = new_ids

    chain.sort(key=lambda j: j.created_at)
    current_id = str(job_id)
    entries = [
        JobHistoryEntry(
            job_id=j.id,
            status=j.status,
            trigger=j.trigger,
            name=j.name,
            created_at=j.created_at,
            updated_at=j.updated_at,
            is_current=(j.id == current_id),
        )
        for j in chain
    ]
    return JobHistoryResponse(entries=entries)


_VALID_TABS = frozenset({"plan", "editor", "report"})


@router.post("/jobs/{job_id}/versions", response_model=SaveVersionResponse, status_code=201)
async def save_job_version(
    job_id: uuid.UUID,
    request: SaveVersionRequest,
    tab: str,
    session: AsyncSession = Depends(get_async_session),
) -> SaveVersionResponse:
    """Save a new version snapshot for a specific editor tab.

    Writes the snapshot to ``job_versions`` and syncs write-through fields on the
    parent ``Job`` row (``python_code`` for editor, ``doc`` for report, and
    ``user_overrides["block_overrides"]`` for plan).

    Args:
        job_id: UUID of the migration job.
        request: Content dict and optional trigger label.
        tab: One of ``plan``, ``editor``, ``report``.
        session: Injected async database session.

    Returns:
        SaveVersionResponse with the new version ID and creation timestamp.

    Raises:
        HTTPException: 404 if the job does not exist, 422 if tab is invalid.
    """
    if tab not in _VALID_TABS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid tab '{tab}'. Must be one of: {sorted(_VALID_TABS)}.",
        )

    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    version = JobVersion(
        id=str(uuid.uuid4()),
        job_id=str(job_id),
        tab=tab,
        content=request.content,
        trigger=request.trigger,
    )
    session.add(version)

    # Write-through: sync relevant fields on the parent job.
    update_values: dict[str, Any] = {}
    if tab == "editor" and "python_code" in request.content:
        update_values["python_code"] = request.content["python_code"]
    elif tab == "report" and "doc" in request.content:
        update_values["doc"] = request.content["doc"]
    elif tab == "plan" and "block_overrides" in request.content:
        overrides: dict[str, Any] = dict(job.user_overrides or {})
        overrides["block_overrides"] = request.content["block_overrides"]
        update_values["user_overrides"] = overrides

    if update_values:
        await session.execute(update(Job).where(Job.id == str(job_id)).values(**update_values))

    await session.flush()
    created_at = version.created_at
    await session.commit()

    return SaveVersionResponse(
        id=version.id,
        job_id=version.job_id,
        tab=version.tab,
        created_at=created_at,
    )


@router.get("/jobs/{job_id}/versions", response_model=list[JobVersionSummary])
async def list_job_versions(
    job_id: uuid.UUID,
    tab: str,
    session: AsyncSession = Depends(get_async_session),
) -> list[JobVersionSummary]:
    """Return all version snapshots for a job tab, newest first.

    Args:
        job_id: UUID of the migration job.
        tab: One of ``plan``, ``editor``, ``report``.
        session: Injected async database session.

    Returns:
        List of JobVersionSummary ordered by ``created_at`` descending.

    Raises:
        HTTPException: 404 if the job does not exist, 422 if tab is invalid.
    """
    if tab not in _VALID_TABS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid tab '{tab}'. Must be one of: {sorted(_VALID_TABS)}.",
        )

    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    rows = await session.execute(
        select(JobVersion)
        .where(JobVersion.job_id == str(job_id), JobVersion.tab == tab)
        .order_by(JobVersion.created_at.desc())
    )
    versions = rows.scalars().all()
    return [
        JobVersionSummary(
            id=v.id,
            job_id=v.job_id,
            tab=v.tab,
            trigger=v.trigger,
            created_at=v.created_at,
        )
        for v in versions
    ]


@router.get("/jobs/{job_id}/versions/{version_id}", response_model=JobVersionDetail)
async def get_job_version(
    job_id: uuid.UUID,
    version_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> JobVersionDetail:
    """Return a single version snapshot including its full content.

    Args:
        job_id: UUID of the migration job.
        version_id: ID of the specific version to retrieve.
        session: Injected async database session.

    Returns:
        JobVersionDetail with the full content dict.

    Raises:
        HTTPException: 404 if the version does not exist or belongs to a different job.
    """
    result = await session.execute(
        select(JobVersion).where(
            JobVersion.id == version_id,
            JobVersion.job_id == str(job_id),
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found.")

    return JobVersionDetail(
        id=version.id,
        job_id=version.job_id,
        tab=version.tab,
        trigger=version.trigger,
        created_at=version.created_at,
        content=version.content,
    )


def _build_translation_router() -> TranslationRouter:
    """Construct a TranslationRouter with default agents.

    Returns:
        A TranslationRouter ready for single-block translation.
    """
    return TranslationRouter(
        data_step_agent=DataStepAgent(),
        proc_agent=ProcAgent(),
        stub_generator=StubGenerator(),
        generic_proc_agent=GenericProcAgent(),
    )


def _replace_block_in_code(
    full_code: str, source_file: str, start_line: int, new_block: str
) -> str:
    """Replace a single block's code in the full assembled python_code string.

    Finds the provenance comment ``# SAS: source_file:start_line`` and replaces
    the text up to (but not including) the next provenance comment or EOF.

    Args:
        full_code: The full assembled python_code string.
        source_file: Source SAS file name.
        start_line: 1-based start line of the block in the source file.
        new_block: Replacement Python code for the block.

    Returns:
        Updated python_code with the block replaced. Returns full_code unchanged
        if the provenance marker is not found.
    """
    marker = f"# SAS: {source_file}:{start_line}"
    idx = full_code.find(marker)
    if idx == -1:
        return full_code

    # Find the start of the provenance marker line (go back to start of line)
    line_start = full_code.rfind("\n", 0, idx)
    line_start = line_start + 1 if line_start != -1 else 0

    # Find the next provenance comment after this one
    next_marker_idx = full_code.find("# SAS:", idx + len(marker))
    if next_marker_idx == -1:
        # This is the last block — replace to end of string
        block_end = len(full_code)
    else:
        # Go back to the start of the next marker's line
        prev_newline = full_code.rfind("\n", idx, next_marker_idx)
        block_end = prev_newline + 1 if prev_newline != -1 else next_marker_idx

    replacement = new_block if new_block.endswith("\n") else new_block + "\n"
    return full_code[:line_start] + replacement + full_code[block_end:]


@router.post("/jobs/{job_id}/blocks/{block_id:path}/refine", response_model=BlockRefineResponse)
async def refine_block(
    job_id: uuid.UUID,
    block_id: str,
    request: BlockRefineRequest,
    session: AsyncSession = Depends(get_async_session),
) -> BlockRefineResponse:
    """Re-translate a single SAS block in-process and persist the revision.

    Translates the specified block using the current translator pipeline, applies
    user notes and hint into the translation context, runs reconciliation, persists
    a BlockRevision row, and updates job.python_code.

    Args:
        job_id: UUID of the migration job.
        block_id: Block identifier in ``basename.sas:start_line`` form (URL-encoded).
        request: Optional notes and hint to guide the LLM retranslation.
        session: Injected async database session.

    Returns:
        BlockRefineResponse with the new revision number, confidence, and
        reconciliation status.

    Raises:
        HTTPException: 404 if job or block not found; 409 if job is accepted.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Job has been accepted and cannot be refined.")

    # Find the BlockPlan for this block_id
    migration_plan: dict[str, Any] | None = job.migration_plan
    block_plan_data: dict[str, Any] | None = None
    if migration_plan:
        for bp in migration_plan.get("block_plans", []):
            if bp.get("block_id") == block_id:
                block_plan_data = bp
                break

    # Parse block_id to extract source_file and start_line
    colon_idx = block_id.rfind(":")
    if colon_idx == -1:
        raise HTTPException(status_code=404, detail=f"Block '{block_id}' not found.")
    source_file = block_id[:colon_idx]
    try:
        start_line = int(block_id[colon_idx + 1 :])
    except ValueError:
        raise HTTPException(  # noqa: B904
            status_code=404, detail=f"Block '{block_id}' not found."
        )

    source_text = (job.files or {}).get(source_file)
    if source_text is None:
        raise HTTPException(status_code=404, detail=f"Source file '{source_file}' not found.")

    # Re-parse the file and find the matching block
    parse_result = SASParser().parse({source_file: source_text})
    target_block: SASBlock | None = next(
        (b for b in parse_result.blocks if b.start_line == start_line), None
    )
    if target_block is None:
        raise HTTPException(
            status_code=404,
            detail=f"Block '{block_id}' not found in parsed output.",
        )

    # Build risk_flags from notes and hint
    risk_flags: list[str] = []
    if request.notes:
        risk_flags.append(f"user_instruction: {request.notes}")
    if request.hint:
        risk_flags.append(f"retry_hint: {request.hint}")

    context = JobContext(
        source_files={source_file: source_text},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=risk_flags,
        blocks=[target_block],
        generated=[],
    )

    # Translate the block
    router = _build_translation_router()
    translator = router.route(target_block)
    gb = await translator.translate(target_block, context)

    # Determine strategy and confidence
    strategy = block_plan_data.get("strategy", "translate") if block_plan_data else "translate"

    # Determine next revision_number
    rev_result = await session.execute(
        select(BlockRevision)
        .where(BlockRevision.job_id == str(job_id), BlockRevision.block_id == block_id)
        .order_by(BlockRevision.revision_number.desc())
    )
    existing_revisions = rev_result.scalars().all()
    is_first_refine = len(existing_revisions) == 0

    if is_first_refine:
        # Insert revision 1 = prior code (from job.python_code, extracted by provenance)
        prior_code = job.python_code or ""
        rev1 = BlockRevision(
            id=str(uuid.uuid4()),
            job_id=str(job_id),
            block_id=block_id,
            revision_number=1,
            python_code=prior_code,
            strategy=strategy,
            confidence="high",
            uncertainty_notes=[],
            trigger="agent",
            notes=None,
            hint=None,
            diff_vs_previous=None,
        )
        session.add(rev1)
        next_revision_number = 2
        prior_python_code = prior_code
    else:
        next_revision_number = existing_revisions[0].revision_number + 1
        prior_python_code = existing_revisions[0].python_code

    # Compute diff vs prior
    diff_lines = list(
        difflib.unified_diff(
            prior_python_code.splitlines(keepends=True),
            gb.python_code.splitlines(keepends=True),
            fromfile=f"{block_id}@rev{next_revision_number - 1}",
            tofile=f"{block_id}@rev{next_revision_number}",
        )
    )
    diff_vs_previous = "".join(diff_lines) if diff_lines else ""

    # Reassemble full python_code by replacing the block's code
    current_full_code = job.python_code or ""
    new_full_code = _replace_block_in_code(
        current_full_code, source_file, start_line, gb.python_code
    )

    # Run reconciliation
    ref_csv_path: str = str((job.files or {}).get("__ref_csv__", ""))
    ref_sas7bdat_path: str = str((job.files or {}).get("__ref_sas7bdat__", ""))
    reconciliation_status: str | None = None
    try:
        backend = LocalBackend()
        recon_report = await asyncio.to_thread(
            ReconciliationService().run,
            ref_csv_path,
            new_full_code,
            backend,
            ref_sas7bdat_path,
        )
        if isinstance(recon_report, dict):
            checks = recon_report.get("checks", [])
            passed = all(c.get("status") == "pass" for c in checks) if checks else True
        else:
            passed = getattr(recon_report, "passed", True)
        reconciliation_status = "pass" if passed else "fail"
    except Exception as exc:
        logger.warning(
            "Block refine reconciliation failed for job %s block %s: %s",
            job_id,
            block_id,
            exc,
        )
        reconciliation_status = "fail"

    # Persist new revision
    new_revision = BlockRevision(
        id=str(uuid.uuid4()),
        job_id=str(job_id),
        block_id=block_id,
        revision_number=next_revision_number,
        python_code=gb.python_code,
        strategy=strategy,
        confidence=gb.confidence,
        uncertainty_notes=gb.uncertainty_notes,
        reconciliation_status=reconciliation_status,
        trigger="human-refine",
        notes=request.notes,
        hint=request.hint,
        diff_vs_previous=diff_vs_previous,
    )
    session.add(new_revision)

    # Update job.python_code and updated_at
    await session.execute(
        update(Job)
        .where(Job.id == str(job_id))
        .values(python_code=new_full_code, updated_at=datetime.now(UTC))
    )
    await session.commit()

    return BlockRefineResponse(
        block_id=block_id,
        revision_number=next_revision_number,
        confidence=gb.confidence,
        reconciliation_status=reconciliation_status,
        python_code=new_full_code,
    )


@router.get(
    "/jobs/{job_id}/blocks/{block_id:path}/revisions", response_model=BlockRevisionListResponse
)
async def get_block_revisions(
    job_id: uuid.UUID,
    block_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> BlockRevisionListResponse:
    """Return all block revisions for a given block, newest first.

    Args:
        job_id: UUID of the migration job.
        block_id: Block identifier in ``basename.sas:start_line`` form.
        session: Injected async database session.

    Returns:
        BlockRevisionListResponse with all revisions ordered by revision_number descending.

    Raises:
        HTTPException: 404 if the job does not exist.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    rows = await session.execute(
        select(BlockRevision)
        .where(BlockRevision.job_id == str(job_id), BlockRevision.block_id == block_id)
        .order_by(BlockRevision.revision_number.desc())
    )
    revisions = rows.scalars().all()
    return BlockRevisionListResponse(
        block_id=block_id,
        revisions=[
            BlockRevisionResponse(
                id=r.id,
                job_id=r.job_id,
                block_id=r.block_id,
                revision_number=r.revision_number,
                python_code=r.python_code,
                strategy=r.strategy,
                confidence=r.confidence,
                uncertainty_notes=r.uncertainty_notes,
                reconciliation_status=r.reconciliation_status,
                trigger=r.trigger,
                notes=r.notes,
                hint=r.hint,
                diff_vs_previous=r.diff_vs_previous,
                created_at=r.created_at,
            )
            for r in revisions
        ],
    )


@router.post(
    "/jobs/{job_id}/blocks/{block_id:path}/revisions/{revision_id}/restore",
    response_model=BlockRefineResponse,
)
async def restore_block_revision(
    job_id: uuid.UUID,
    block_id: str,
    revision_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> BlockRefineResponse:
    """Restore a block to a previous revision, inserting a new revision with trigger=restore.

    Loads the specified revision, computes a diff vs current job.python_code, inserts a new
    revision row, reassembles the full python_code, and persists the updated job.

    Args:
        job_id: UUID of the migration job.
        block_id: Block identifier in ``basename.sas:start_line`` form.
        revision_id: ID of the revision to restore.
        session: Injected async database session.

    Returns:
        BlockRefineResponse with the new revision number.

    Raises:
        HTTPException: 404 if job or revision not found; 409 if job is accepted.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Job has been accepted and cannot be refined.")

    # Load the target revision
    rev_result = await session.execute(
        select(BlockRevision).where(
            BlockRevision.id == revision_id,
            BlockRevision.job_id == str(job_id),
            BlockRevision.block_id == block_id,
        )
    )
    target_revision = rev_result.scalar_one_or_none()
    if target_revision is None:
        raise HTTPException(status_code=404, detail=f"Revision '{revision_id}' not found.")

    # Get current max revision number
    all_revs_result = await session.execute(
        select(BlockRevision)
        .where(BlockRevision.job_id == str(job_id), BlockRevision.block_id == block_id)
        .order_by(BlockRevision.revision_number.desc())
    )
    all_revisions = all_revs_result.scalars().all()
    next_revision_number = (all_revisions[0].revision_number + 1) if all_revisions else 1

    # Compute diff vs current job.python_code
    current_full_code = job.python_code or ""
    diff_lines = list(
        difflib.unified_diff(
            current_full_code.splitlines(keepends=True),
            target_revision.python_code.splitlines(keepends=True),
            fromfile=f"{block_id}@current",
            tofile=f"{block_id}@restore-{target_revision.revision_number}",
        )
    )
    diff_vs_previous = "".join(diff_lines) if diff_lines else ""

    # Parse block_id to extract source_file and start_line
    colon_idx = block_id.rfind(":")
    source_file = block_id[:colon_idx] if colon_idx != -1 else block_id
    try:
        start_line = int(block_id[colon_idx + 1 :]) if colon_idx != -1 else 0
    except ValueError:
        start_line = 0

    # Reassemble full python_code
    new_full_code = _replace_block_in_code(
        current_full_code, source_file, start_line, target_revision.python_code
    )

    # Insert new restore revision
    restore_revision = BlockRevision(
        id=str(uuid.uuid4()),
        job_id=str(job_id),
        block_id=block_id,
        revision_number=next_revision_number,
        python_code=target_revision.python_code,
        strategy=target_revision.strategy,
        confidence=target_revision.confidence,
        uncertainty_notes=target_revision.uncertainty_notes,
        reconciliation_status=target_revision.reconciliation_status,
        trigger="restore",
        notes=None,
        hint=None,
        diff_vs_previous=diff_vs_previous,
    )
    session.add(restore_revision)

    # Update job.python_code
    await session.execute(
        update(Job)
        .where(Job.id == str(job_id))
        .values(python_code=new_full_code, updated_at=datetime.now(UTC))
    )
    await session.commit()

    return BlockRefineResponse(
        block_id=block_id,
        revision_number=next_revision_number,
        confidence=target_revision.confidence,
        reconciliation_status=target_revision.reconciliation_status,
        python_code=new_full_code,
    )


# ---------------------------------------------------------------------------
# S6 — Job-level changelog
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}/changelog", response_model=JobChangelogResponse)
async def get_job_changelog(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> JobChangelogResponse:
    """Return all block revision entries for a job, newest first.

    Args:
        job_id: UUID of the migration job.
        session: Injected async database session.

    Returns:
        JobChangelogResponse listing every BlockRevision ordered by created_at DESC.

    Raises:
        HTTPException: 404 if the job does not exist.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    rows = await session.execute(
        select(BlockRevision)
        .where(BlockRevision.job_id == str(job_id))
        .order_by(BlockRevision.created_at.desc())
    )
    revisions = rows.scalars().all()

    entries = [
        ChangelogEntry(
            id=r.id,
            block_id=r.block_id,
            revision_number=r.revision_number,
            trigger=r.trigger,
            strategy=r.strategy,
            confidence=r.confidence,
            reconciliation_status=r.reconciliation_status,
            notes=r.notes,
            hint=r.hint,
            diff_vs_previous=r.diff_vs_previous,
            created_at=r.created_at,
        )
        for r in revisions
    ]
    return JobChangelogResponse(job_id=str(job_id), entries=entries)


# ---------------------------------------------------------------------------
# S7 — Tiered trust report
# ---------------------------------------------------------------------------

_MANUAL_STRATEGIES = frozenset({"manual", "manual_ingestion", "skip"})
_AUTO_VERIFIED_CONFIDENCES = frozenset({"verified_high", "verified_medium"})
_CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2, "unknown": -1}


def _blast_radius_map(cross_file_edges: list[dict[str, Any]]) -> dict[str, int]:
    """Count downstream edges per source file from cross-file lineage edges.

    Args:
        cross_file_edges: List of edge dicts with ``source_file`` keys.

    Returns:
        Mapping from source_file to count of outgoing edges.
    """
    counts: dict[str, int] = {}
    for edge in cross_file_edges:
        src = edge.get("source_file", "")
        if src:
            counts[src] = counts.get(src, 0) + 1
    return counts


def _block_sort_key(block: TrustReportBlock) -> tuple[int, int, int]:
    """Return a sort key: needs_attention DESC, blast_radius DESC, confidence ASC."""
    attention = 0 if block.needs_attention else 1
    radius = -(block.blast_radius if block.blast_radius is not None else -1)
    confidence_rank = _CONFIDENCE_ORDER.get(block.self_confidence, -1)
    return (attention, radius, confidence_rank)


def _aggregate_file_metrics(
    blocks: list[TrustReportBlock],
) -> list[TrustReportFile]:
    """Group blocks by source_file and compute per-file aggregates.

    Args:
        blocks: Flat list of TrustReportBlock instances.

    Returns:
        List of TrustReportFile with aggregated counts.
    """
    file_map: dict[str, list[TrustReportBlock]] = {}
    for b in blocks:
        file_map.setdefault(b.source_file, []).append(b)

    result: list[TrustReportFile] = []
    for source_file, file_blocks in file_map.items():
        result.append(
            TrustReportFile(
                source_file=source_file,
                total_blocks=len(file_blocks),
                auto_verified=sum(
                    1 for b in file_blocks if b.verified_confidence in _AUTO_VERIFIED_CONFIDENCES
                ),
                needs_review=sum(
                    1
                    for b in file_blocks
                    if b.needs_attention and b.strategy not in _MANUAL_STRATEGIES
                ),
                manual_todo=sum(1 for b in file_blocks if b.strategy in _MANUAL_STRATEGIES),
                failed_reconciliation=sum(
                    1 for b in file_blocks if b.reconciliation_status == "fail"
                ),
            )
        )
    return result


def _overall_confidence(total: int, auto_verified: int) -> str:
    """Compute overall confidence label from auto-verified ratio.

    Args:
        total: Total number of blocks.
        auto_verified: Number of auto-verified blocks.

    Returns:
        ``"unknown"`` if no blocks; ``"high"`` />80%, ``"medium"`` />50%,
        ``"low"`` otherwise.
    """
    if total == 0:
        return "unknown"
    ratio = auto_verified / total
    if ratio > 0.8:
        return "high"
    if ratio > 0.5:
        return "medium"
    return "low"


@router.get("/jobs/{job_id}/trust-report", response_model=TrustReportResponse)
async def get_job_trust_report(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> TrustReportResponse:
    """Return a tiered trust report for all blocks in a completed migration job.

    Aggregates confidence, reconciliation status, and blast radius for every
    block in the migration plan. Blocks are sorted by needs_attention DESC,
    blast_radius DESC, then self_confidence ASC.

    Args:
        job_id: UUID of the migration job.
        session: Injected async database session.

    Returns:
        TrustReportResponse with block-level and file-level trust aggregates.

    Raises:
        HTTPException: 404 if the job does not exist.
    """
    result = await session.execute(select(Job).where(Job.id == str(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    # If job not yet in a reviewable state, return an empty report.
    if job.status not in ("proposed", "accepted", "done") or job.migration_plan is None:
        return TrustReportResponse(
            job_id=str(job_id),
            lineage_available=job.lineage is not None,
            overall_confidence="unknown",
            total_blocks=0,
            auto_verified=0,
            needs_review=0,
            manual_todo=0,
            failed_reconciliation=0,
            files=[],
            blocks=[],
            review_queue=[],
        )

    # Build block_confidence map from lineage if available.
    lineage: dict[str, Any] = job.lineage or {}
    block_confidence: dict[str, Any] = lineage.get("block_confidence", {})
    cross_file_edges: list[dict[str, Any]] = lineage.get("cross_file_edges", [])
    blast_map = _blast_radius_map(cross_file_edges)

    # Query the most recent BlockRevision per block_id (Python-side groupby).
    rev_rows = await session.execute(
        select(BlockRevision)
        .where(BlockRevision.job_id == str(job_id))
        .order_by(BlockRevision.block_id, BlockRevision.revision_number.desc())
    )
    all_revisions = rev_rows.scalars().all()

    latest_revision: dict[str, BlockRevision] = {}
    for rev in all_revisions:
        if rev.block_id not in latest_revision:
            latest_revision[rev.block_id] = rev

    # Build TrustReportBlock list from migration_plan.block_plans.
    block_plans: list[dict[str, Any]] = job.migration_plan.get("block_plans", [])
    blocks: list[TrustReportBlock] = []

    for bp in block_plans:
        block_id: str = bp.get("block_id", "")
        source_file: str = bp.get("source_file", "")
        strategy: str = bp.get("strategy", "translate")

        conf_entry: dict[str, Any] = block_confidence.get(block_id, {})
        self_confidence: str = conf_entry.get("confidence", "unknown")
        verified_confidence: str | None = conf_entry.get("verified_confidence")

        latest_rev: BlockRevision | None = latest_revision.get(block_id)
        reconciliation_status: str | None = latest_rev.reconciliation_status if latest_rev else None

        needs_attention: bool = (
            verified_confidence in ("verified_low", None) and reconciliation_status == "fail"
        ) or strategy in _MANUAL_STRATEGIES

        radius: int | None = blast_map.get(source_file) if lineage else None

        blocks.append(
            TrustReportBlock(
                block_id=block_id,
                source_file=source_file,
                start_line=bp.get("start_line", 0),
                block_type=bp.get("block_type", ""),
                strategy=strategy,
                self_confidence=self_confidence,
                verified_confidence=verified_confidence,
                reconciliation_status=reconciliation_status,
                needs_attention=needs_attention,
                blast_radius=radius,
            )
        )

    blocks.sort(key=_block_sort_key)

    total = len(blocks)
    auto_verified = sum(1 for b in blocks if b.verified_confidence in _AUTO_VERIFIED_CONFIDENCES)
    manual_todo = sum(1 for b in blocks if b.strategy in _MANUAL_STRATEGIES)
    failed_reconciliation = sum(1 for b in blocks if b.reconciliation_status == "fail")
    needs_review = sum(
        1 for b in blocks if b.needs_attention and b.strategy not in _MANUAL_STRATEGIES
    )

    return TrustReportResponse(
        job_id=str(job_id),
        lineage_available=job.lineage is not None,
        overall_confidence=_overall_confidence(total, auto_verified),
        total_blocks=total,
        auto_verified=auto_verified,
        needs_review=needs_review,
        manual_todo=manual_todo,
        failed_reconciliation=failed_reconciliation,
        files=_aggregate_file_metrics(blocks),
        blocks=blocks,
        review_queue=[b for b in blocks if b.needs_attention],
    )
