"""Trace emitter for per-job execution audit events.

Inserts :class:`JobTrace` rows into the database for every significant pipeline
milestone (block_start, block_done, recon_result, job_done, error).  Failures
inside :meth:`TraceEmitter.emit` are swallowed and logged as warnings so that
tracing never disrupts the main pipeline.
"""

# SAS: src/worker/engine/trace.py:1

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from src.backend.db.models import JobTrace

logger = logging.getLogger(__name__)


class JobCancelledError(Exception):
    """Raised when a job's cancellation_requested flag is set between blocks."""


class TraceEmitter:
    """Emits immutable audit trace events into the job_traces table.

    Each call to :meth:`emit` opens a *separate* short-lived session so that
    trace writes are committed independently from the main job session.  This
    means traces are visible in the DB even if the job session is rolled back.

    Args:
        job_id: The UUID string of the job being traced.
        session_factory: An :class:`async_sessionmaker` bound to the worker's
            async engine.
    """

    def __init__(self, job_id: str, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise the emitter for a specific job.

        Args:
            job_id: UUID string of the job.
            session_factory: Async session factory used to open trace sessions.
        """
        self._job_id = job_id
        self._session_factory = session_factory

    async def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Insert a JobTrace row into the database.

        Adds a UTC timestamp under the ``ts`` key before persisting.  Never
        raises — all exceptions are caught and logged as WARNING.

        Args:
            event_type: One of ``block_start``, ``block_done``, ``recon_result``,
                ``job_done``, ``error``, ``phase_start``, ``phase_done``,
                ``parse_result``, ``plan_result``, ``enrichment_item_done``,
                or any custom event name.
            payload: Arbitrary JSON-serialisable dict of event data.
        """
        enriched: dict[str, Any] = {
            **payload,
            "ts": datetime.now(UTC).isoformat(),
        }
        try:
            async with self._session_factory() as session:
                trace = JobTrace(
                    job_id=self._job_id,
                    event_type=event_type,
                    payload=enriched,
                )
                session.add(trace)
                await session.commit()
        except Exception as exc:
            logger.warning(
                "TraceEmitter: failed to persist event %s for job %s: %s",
                event_type,
                self._job_id,
                exc,
            )
