"""GET /jobs/{id} — retrieve job status, audit record, and downloadable artefacts."""

import io
import json
import logging
import uuid
import zipfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.backend.api.schemas import AuditResponse, JobStatusResponse
from src.backend.db.models import Job
from src.backend.db.session import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter()


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
    )


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
