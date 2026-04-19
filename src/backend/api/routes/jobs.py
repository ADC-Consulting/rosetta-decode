"""GET /jobs/{id} — retrieve job status, audit record, and downloadable artefacts."""

import io
import json
import logging
import uuid
import zipfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.backend.api.schemas import (
    AuditResponse,
    JobDocResponse,
    JobLineageResponse,
    JobListResponse,
    JobSourcesResponse,
    JobStatusResponse,
    JobSummary,
)
from src.backend.db.models import Job
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
    if job.status != "done":
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
    return JobLineageResponse(**{**job.lineage, "job_id": job_id})


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
