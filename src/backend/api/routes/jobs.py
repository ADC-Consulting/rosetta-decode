"""GET /jobs/{id} — retrieve job status and results."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.backend.api.schemas import JobStatusResponse
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
