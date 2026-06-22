"""POST /migrate — accept SAS files or a zip archive, create a migration job."""

import hashlib
import io
import logging
import os
import uuid
import zipfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from src.backend.api.schemas import FileRejection, MigrateResponse
from src.backend.core.config import backend_settings
from src.backend.db.models import Job
from src.backend.db.session import get_async_session
from src.worker.engine.parser import SASParser
from src.worker.engine.scoping import build_scoping_report

logger = logging.getLogger(__name__)

router = APIRouter()

_ACCEPTED_ZIP_EXTS = {".sas", ".sas7bdat", ".xpt", ".xport", ".csv", ".log", ".xlsx", ".xls"}

# F77: valid values for the `mode` form param. "migrate" runs the async worker
# pipeline; "scope" runs a synchronous, LLM-free static assessment in-request.
_VALID_MODES = {"migrate", "scope"}


def _unpack_zip(
    raw: bytes, upload_dir: str, job_id: str
) -> tuple[dict[str, str], list[str], list[FileRejection]]:
    """Extract files from a zip archive into file_contents and disk.

    Args:
        raw: Raw bytes of the zip archive.
        upload_dir: Directory where non-SAS files are written.
        job_id: Job identifier used to namespace saved files.

    Returns:
        Tuple of (file_contents, accepted_names, rejected_list).
    """
    file_contents: dict[str, str] = {}
    accepted: list[str] = []
    rejected: list[FileRejection] = []

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            # Normalise to forward slashes and strip leading slash
            norm_path = info.filename.replace("\\", "/").lstrip("/")
            name = os.path.basename(norm_path)
            if not name:
                continue
            # macOS resource fork / metadata files — skip silently
            if name.startswith("._") or norm_path.startswith("__MACOSX/"):
                continue
            # Path traversal guard — reject any component that tries to escape
            if ".." in norm_path.split("/"):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in _ACCEPTED_ZIP_EXTS:
                rejected.append(
                    FileRejection(
                        filename=norm_path, reason=f"Unsupported file type: {ext or '(none)'}"
                    )
                )
                continue
            data = zf.read(info.filename)
            if ext == ".sas":
                file_contents[norm_path] = data.decode("utf-8", errors="replace")
            else:
                job_dir = os.path.join(upload_dir, job_id)
                os.makedirs(job_dir, exist_ok=True)
                dest = os.path.join(job_dir, name)
                with open(dest, "wb") as fh:
                    fh.write(data)
                sentinel = f"__ref_{ext.lstrip('.')}_{norm_path}__"
                file_contents[sentinel] = dest
            accepted.append(norm_path)

    return file_contents, accepted, rejected


@router.post("/migrate", response_model=MigrateResponse, status_code=200)
async def migrate(
    sas_files: list[UploadFile] = File(default=[]),
    session: AsyncSession = Depends(get_async_session),
    ref_dataset: UploadFile | None = None,
    zip_file: UploadFile | None = None,
    ref_csv: UploadFile | None = None,
    name: str | None = Form(default=None),
    ref_target_path: str | None = Form(default=None),
    mode: str = Form(default="migrate"),
) -> MigrateResponse:
    """Accept SAS files or a zip archive and enqueue a migration job.

    Args:
        sas_files: One or more uploaded .sas files (mutually exclusive with zip_file).
        session: Injected async database session.
        ref_dataset: Optional .sas7bdat reference dataset for reconciliation.
        zip_file: A zip archive of SAS and supporting files (mutually exclusive with sas_files).
        ref_csv: Optional .csv reference dataset stored as ``__ref_csv__`` for reconciliation.
        name: Optional human-readable label for the migration job.
        ref_target_path: Optional path of a zip-extracted file to promote as the canonical
            reconciliation reference (``__ref_csv__`` or ``__ref_sas7bdat__``).
        mode: ``"migrate"`` (default) enqueues the async worker pipeline; ``"scope"`` runs a
            synchronous, LLM-free static assessment in-request and returns a ``done`` job.

    Returns:
        MigrateResponse with job UUID, accepted file list, and any rejected files.

    Raises:
        HTTPException: 400 if inputs conflict or are invalid; 413 if zip exceeds size limit.
    """
    if mode not in _VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"mode must be one of {sorted(_VALID_MODES)}; got '{mode}'.",
        )

    has_sas = bool(sas_files)
    has_zip = zip_file is not None

    if has_sas and has_zip:
        raise HTTPException(
            status_code=400,
            detail="Provide either sas_files or zip_file, not both.",
        )
    if not has_sas and not has_zip:
        raise HTTPException(status_code=400, detail="At least one .sas file is required.")

    job_id = str(uuid.uuid4())
    hasher = hashlib.sha256()
    file_contents: dict[str, str]
    accepted: list[str]
    rejected: list[FileRejection]

    if has_zip:
        zip_raw = await zip_file.read()  # type: ignore[union-attr]
        if len(zip_raw) > backend_settings.max_zip_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Zip archive exceeds the {backend_settings.max_zip_bytes} byte limit.",
            )
        hasher.update(zip_raw)
        file_contents, accepted, rejected = _unpack_zip(
            zip_raw, backend_settings.upload_dir, job_id
        )
        if not file_contents:
            raise HTTPException(status_code=400, detail="Zip contained no supported files.")
    else:
        file_contents = {}
        accepted = []
        rejected = []
        for upload in sas_files:
            filename = upload.filename or "unnamed.sas"
            if not filename.lower().endswith(".sas"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Only .sas files are accepted; got '{filename}'.",
                )
            raw = await upload.read()
            file_contents[filename] = raw.decode("utf-8", errors="replace")
            hasher.update(raw)
            accepted.append(filename)

        if ref_dataset is not None:
            ref_name = ref_dataset.filename or "unnamed"
            if not ref_name.lower().endswith(".sas7bdat"):
                raise HTTPException(
                    status_code=400,
                    detail=f"ref_dataset must be a .sas7bdat file; got '{ref_name}'.",
                )
            ref_raw = await ref_dataset.read()
            hasher.update(ref_raw)
            job_dir = os.path.join(backend_settings.upload_dir, job_id)
            os.makedirs(job_dir, exist_ok=True)
            dest_path = os.path.join(job_dir, ref_name)
            with open(dest_path, "wb") as fh:
                fh.write(ref_raw)
            file_contents["__ref_sas7bdat__"] = dest_path

        if ref_csv is not None:
            ref_csv_name = ref_csv.filename or "reference.csv"
            if not ref_csv_name.lower().endswith(".csv"):
                raise HTTPException(
                    status_code=400,
                    detail=f"ref_csv must be a .csv file; got '{ref_csv_name}'.",
                )
            csv_raw = await ref_csv.read()
            hasher.update(csv_raw)
            job_dir = os.path.join(backend_settings.upload_dir, job_id)
            os.makedirs(job_dir, exist_ok=True)
            dest_path = os.path.join(job_dir, ref_csv_name)
            with open(dest_path, "wb") as fh:
                fh.write(csv_raw)
            file_contents["__ref_csv__"] = dest_path

    # Promote a zip-extracted file to the canonical __ref_csv__ / __ref_sas7bdat__ sentinel
    if ref_target_path:
        ext = os.path.splitext(ref_target_path)[1].lower()
        norm_target = ref_target_path.replace("\\", "/")
        for key, disk_path in file_contents.items():
            if (
                key.startswith(f"__ref_{ext.lstrip('.')}_")
                and key.endswith("__")
                and norm_target in key
            ):
                if ext == ".csv":
                    file_contents["__ref_csv__"] = disk_path
                elif ext == ".sas7bdat":
                    file_contents["__ref_sas7bdat__"] = disk_path
                break

    input_hash = hasher.hexdigest()

    if mode == "scope":
        # F77: synchronous, LLM-free assessment. Parse off the event loop, build the
        # report, persist a job already in "done" state. The worker never sees it
        # (status is never "queued"), so no main.py / queue involvement and no tokens.
        job = await _build_scope_job(job_id, input_hash, file_contents, name)
        session.add(job)
        await session.commit()
        logger.info("Scope job %s created (hash=%s)", job_id, input_hash[:12])
        return MigrateResponse(job_id=uuid.UUID(job_id), accepted=accepted, rejected=rejected)

    job = Job(
        id=job_id,
        status="queued",
        input_hash=input_hash,
        files=file_contents,
        name=name,
    )
    session.add(job)
    await session.commit()

    logger.info("Job %s created (hash=%s)", job_id, input_hash[:12])
    return MigrateResponse(job_id=uuid.UUID(job_id), accepted=accepted, rejected=rejected)


async def _build_scope_job(
    job_id: str, input_hash: str, file_contents: dict[str, str], name: str | None
) -> Job:
    """Parse SAS sources synchronously and build a ``done`` scope job (no LLM).

    Args:
        job_id: Pre-generated job UUID string.
        input_hash: SHA-256 hash of the uploaded inputs.
        file_contents: Full file map (real ``.sas`` keys plus ``__ref_*`` sentinels).
        name: Optional human-readable job label.

    Returns:
        A :class:`Job` with ``status="done"``, ``mode="scope"`` and the persisted
        ``scoping_report``. CPU-bound parse runs in a threadpool to keep the event
        loop free.
    """
    # Real .sas sources only — skip sentinel/data keys for the parser input.
    sas_sources = {k: v for k, v in file_contents.items() if _is_sas_source(k)}
    parse_result = await run_in_threadpool(SASParser().parse, sas_sources)
    report = build_scoping_report(parse_result, file_contents)
    return Job(
        id=job_id,
        status="done",
        mode="scope",
        input_hash=input_hash,
        files=file_contents,
        name=name,
        scoping_report=report.model_dump(),
    )


def _is_sas_source(key: str) -> bool:
    """Return True for genuine ``.sas`` source keys (skips ``__ref_*`` sentinels)."""
    return key.lower().endswith(".sas") and not key.startswith("__")
