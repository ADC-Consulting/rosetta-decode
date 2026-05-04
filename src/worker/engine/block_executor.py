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
        session_dir: str = "",
        ref_csv_path: str = "",
        ref_sas7bdat_path: str = "",
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
            session_dir: If non-empty, path to the per-job DataFrame parquet cache so
                prior blocks' DataFrames are pre-loaded before this block runs.
            ref_csv_path: Path to reference CSV for reconciliation checks.
            ref_sas7bdat_path: Path to reference .sas7bdat for reconciliation checks.

        Returns:
            A ``{"checks": [...]}`` dict on success, or ``None`` on exception /
            when no reference data checks were executed.
        """
        effective_data_dir = data_dir or ""
        remote = RemoteReconciliationService()
        try:
            result: ReconResult = await remote.run(
                ref_csv_path,
                python_code,
                backend,
                ref_sas7bdat_path,
                data_dir=effective_data_dir,
                session_dir=session_dir,
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
            if ref_csv_path or ref_sas7bdat_path:
                # Ref provided but no checks returned — code likely crashed.
                # Synthetic failure so the retry loop fires.
                crash_check = {
                    "name": "execution",
                    "status": "fail",
                    "detail": "no checks returned (runtime crash)",
                }
                return {"checks": [crash_check]}
            # No ref data at all — genuine no-op, treat as pass
            return None

        return result
