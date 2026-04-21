"""GET /jobs/{id} — retrieve job status, audit record, and downloadable artefacts."""

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
    UpdatePythonCodeRequest,
)
from src.backend.db.models import Job, JobVersion
from src.backend.db.session import get_async_session

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
