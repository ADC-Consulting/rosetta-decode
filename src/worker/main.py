"""Worker service — async poll loop for migration jobs."""

import asyncio
import logging
import sys

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Job
from src.worker.compute.factory import BackendFactory
from src.worker.core.config import worker_settings
from src.worker.engine.codegen import CodeGenerator
from src.worker.engine.llm_client import LLMClient, LLMTranslationError
from src.worker.engine.models import GeneratedBlock
from src.worker.engine.parser import SASParser
from src.worker.validation.reconciliation import ReconciliationService

logging.basicConfig(
    level=getattr(logging, worker_settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create an async SQLAlchemy session factory from settings."""
    engine = create_async_engine(worker_settings.database_url, pool_pre_ping=True)
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def _claim_job(session: AsyncSession) -> Job | None:
    """Atomically claim one queued job by setting status=running.

    Returns:
        The claimed Job, or None if the queue is empty.
    """
    result = await session.execute(
        select(Job).where(Job.status == "queued").limit(1).with_for_update(skip_locked=True)
    )
    job: Job | None = result.scalar_one_or_none()
    if job is None:
        return None

    await session.execute(update(Job).where(Job.id == job.id).values(status="running"))
    await session.commit()
    await session.refresh(job)
    return job


async def _process_job(session: AsyncSession, job: Job) -> None:
    """Run the full migration pipeline for a single job.

    Executes SASParser → LLMClient → CodeGenerator → ReconciliationService in
    order, then persists the results. Sets status=done on success, status=failed
    with error message on any exception.

    Args:
        session: Database session for updating job state.
        job: The claimed job to process.
    """
    logger.info("Processing job %s", job.id)
    try:
        files: dict[str, str] = {k: v for k, v in job.files.items() if k != "__ref_csv__"}
        ref_csv_path: str = str(job.files.get("__ref_csv__", ""))

        result = SASParser().parse(files)
        blocks = result.blocks
        client = LLMClient()
        generated: list[GeneratedBlock] = []
        for idx, block in enumerate(blocks):
            try:
                gb = await asyncio.to_thread(client.translate, block)
                generated.append(gb)
            except LLMTranslationError as exc:
                partial_code = (
                    CodeGenerator().assemble(generated, macro_vars=result.macro_vars)
                    if generated
                    else None
                )
                logger.error(
                    "Job %s failed at block %d/%d: %s",
                    job.id,
                    idx,
                    len(blocks),
                    exc,
                    exc_info=True,
                )
                await session.execute(
                    update(Job)
                    .where(Job.id == job.id)
                    .values(
                        status="failed",
                        error=str(exc),
                        error_detail={
                            "stage": "llm_translation",
                            "block_index": idx,
                            "block_count": len(blocks),
                            "is_transient": exc.is_transient,
                            "resumable": exc.is_transient,
                            "exception_type": (
                                type(exc.cause).__name__ if exc.cause else type(exc).__name__
                            ),
                            **({"python_code": partial_code} if partial_code else {}),
                        },
                        python_code=partial_code,
                    )
                )
                await session.commit()
                return
        python_code = CodeGenerator().assemble(generated, macro_vars=result.macro_vars)

        backend = BackendFactory.create()
        reconciler = ReconciliationService()
        report = await asyncio.to_thread(reconciler.run, ref_csv_path, python_code, backend)

        await session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(
                status="done",
                python_code=python_code,
                report=report,
                llm_model=worker_settings.llm_model,
            )
        )
        await session.commit()
        logger.info("Job %s completed successfully", job.id)
    except Exception as exc:
        logger.warning("Job %s failed: %s", job.id, exc)
        await session.execute(
            update(Job).where(Job.id == job.id).values(status="failed", error=str(exc))
        )
        await session.commit()


async def poll_loop() -> None:
    """Continuously poll for queued jobs and process them."""
    session_factory = _make_session_factory()
    logger.info("Worker started — polling every %ds", worker_settings.poll_interval_seconds)

    while True:
        async with session_factory() as session:
            job = await _claim_job(session)
            if job is not None:
                async with session_factory() as proc_session:
                    await _process_job(proc_session, job)
            else:
                logger.debug("No queued jobs")

        await asyncio.sleep(worker_settings.poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(poll_loop())
