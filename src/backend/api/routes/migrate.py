"""POST /migrate — accept SAS files, create a migration job."""

import hashlib
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from src.backend.api.schemas import MigrateResponse
from src.backend.db.models import Job
from src.backend.db.session import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/migrate", response_model=MigrateResponse, status_code=200)
async def migrate(
    sas_files: list[UploadFile],
    session: AsyncSession = Depends(get_async_session),
) -> MigrateResponse:
    """Accept one or more SAS files and enqueue a migration job.

    Args:
        sas_files: One or more uploaded .sas files.
        session: Injected async database session.

    Returns:
        MigrateResponse containing the new job UUID.

    Raises:
        HTTPException: 400 if no files are provided or a file is not .sas.
    """
    if not sas_files:
        raise HTTPException(status_code=400, detail="At least one .sas file is required.")

    file_contents: dict[str, str] = {}
    hasher = hashlib.sha256()

    for upload in sas_files:
        filename = upload.filename or "unnamed.sas"
        if not filename.lower().endswith(".sas"):
            raise HTTPException(
                status_code=400,
                detail=f"Only .sas files are accepted; got '{filename}'.",
            )
        raw = await upload.read()
        content = raw.decode("utf-8", errors="replace")
        file_contents[filename] = content
        hasher.update(raw)

    input_hash = hasher.hexdigest()
    job_id = str(uuid.uuid4())

    job = Job(
        id=job_id,
        status="queued",
        input_hash=input_hash,
        files=file_contents,
    )
    session.add(job)
    await session.commit()

    logger.info("Job %s created (hash=%s)", job_id, input_hash[:12])
    return MigrateResponse(job_id=uuid.UUID(job_id))
