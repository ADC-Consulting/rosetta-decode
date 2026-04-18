"""POST /migrate — accept SAS files, create a migration job."""

import hashlib
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from src.backend.api.schemas import MigrateResponse
from src.backend.core.config import backend_settings
from src.backend.db.models import Job
from src.backend.db.session import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/migrate", response_model=MigrateResponse, status_code=200)
async def migrate(
    sas_files: list[UploadFile],
    session: AsyncSession = Depends(get_async_session),
    ref_dataset: UploadFile | None = None,
) -> MigrateResponse:
    """Accept one or more SAS files and enqueue a migration job.

    Args:
        sas_files: One or more uploaded .sas files.
        session: Injected async database session.
        ref_dataset: Optional .sas7bdat reference dataset for reconciliation.

    Returns:
        MigrateResponse containing the new job UUID.

    Raises:
        HTTPException: 400 if no files are provided, a file is not .sas, or
            ref_dataset is not a .sas7bdat file.
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

    job_id = str(uuid.uuid4())

    if ref_dataset is not None:
        ref_name = ref_dataset.filename or "unnamed"
        if not ref_name.lower().endswith(".sas7bdat"):
            raise HTTPException(
                status_code=400,
                detail=f"ref_dataset must be a .sas7bdat file; got '{ref_name}'.",
            )
        ref_raw = await ref_dataset.read()
        hasher.update(ref_raw)
        os.makedirs(backend_settings.upload_dir, exist_ok=True)
        dest_filename = f"{job_id}_{ref_name}"
        dest_path = os.path.join(backend_settings.upload_dir, dest_filename)
        with open(dest_path, "wb") as fh:
            fh.write(ref_raw)
        file_contents["__ref_sas7bdat__"] = dest_path

    input_hash = hasher.hexdigest()

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
