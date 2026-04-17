"""Worker service — async poll loop for migration jobs."""

import asyncio
import logging
import sys

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Job
from src.worker.core.config import worker_settings

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

    In this scaffold the pipeline is not yet implemented; the job is
    marked failed with a clear message so downstream polling works correctly.

    Args:
        session: Database session for updating job state.
        job: The claimed job to process.
    """
    logger.info("Processing job %s", job.id)
    try:
        # Migration pipeline not yet implemented — F1/F3 will fill this in
        raise NotImplementedError("Migration pipeline not yet implemented (Phase 1 scaffold)")
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
