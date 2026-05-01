"""BlockExecutor — per-block execute-and-reconcile helper for the F19 refine loop.

Wraps RemoteReconciliationService to run a single translated block through the
executor microservice and return a structured pass/fail result.

# SAS: block_executor.py:1
"""

from __future__ import annotations

import logging
from typing import Any

from src.worker.compute.base import ComputeBackend
from src.worker.validation.reconciliation import RemoteReconciliationService

logger = logging.getLogger(__name__)

# ReconResult mirrors the {"checks": [...]} dict from RemoteReconciliationService
ReconResult = dict[str, Any]


class BlockExecutor:
    """Execute a single translated block via the remote executor and reconcile.

    Returns ``None`` (no-op) when no reference data is available or when the
    executor is unreachable.  Returns a ``{"checks": [...]}`` dict otherwise so
    callers can determine pass/fail.

    Attributes:
        _executor_url: Reserved for future direct HTTP calls; actual URL is read
            from ``worker_settings.executor_url`` inside RemoteReconciliationService.
    """

    def __init__(self, executor_url: str = "http://localhost:8001") -> None:
        """Initialise with an optional executor URL.

        Args:
            executor_url: Reserved for future use; the actual URL is read from
                ``worker_settings.executor_url`` inside RemoteReconciliationService.
        """
        self._executor_url = executor_url

    async def run(
        self,
        python_code: str,
        block_id: str,
        backend: ComputeBackend,
        data_dir: str | None = None,
    ) -> ReconResult | None:
        """Execute *python_code* via the remote executor and return reconciliation results.

        Returns ``None`` when no reference data context is available (treat as
        no-op — the refine loop should continue as if the block passed).  Also
        returns ``None`` on any executor exception (soft-fail, no retry penalty).

        Args:
            python_code: Generated Python source for the block (cumulative slice).
            block_id: Human-readable identifier used in log messages (e.g.
                ``"main.sas:10"``).
            backend: ComputeBackend instance forwarded to RemoteReconciliationService
                for interface parity.
            data_dir: Job-specific upload directory for executor path resolution.
                When ``None``, an empty string is forwarded.

        Returns:
            A ``{"checks": [...]}`` dict on success, or ``None`` on exception /
            when no reference data checks were executed.
        """
        effective_data_dir = data_dir or ""
        remote = RemoteReconciliationService()
        try:
            result: ReconResult = await remote.run(
                "",
                python_code,
                backend,
                "",
                data_dir=effective_data_dir,
            )
        except Exception as exc:
            logger.warning(
                "[BlockExecutor] block %s: executor call failed (%s: %s) — treating as no-op",
                block_id,
                type(exc).__name__,
                exc,
            )
            return None

        checks: list[dict[str, Any]] = result.get("checks", [])
        if not checks:
            # No checks ran — no reference data available; treat as pass (no-op)
            return None

        return result
