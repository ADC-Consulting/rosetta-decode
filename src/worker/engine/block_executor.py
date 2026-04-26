"""BlockExecutor — runs assembled code through reconciliation for a trial set of blocks.

Used by the F19 agentic execute-and-refine loop to test each translated block
before committing it to the final output.

# SAS: block_executor.py:1
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.worker.engine.codegen import CodeGenerator
from src.worker.engine.models import GeneratedBlock, JobContext, ReconciliationReport
from src.worker.validation.reconciliation import ReconciliationService

logger = logging.getLogger(__name__)


def _to_report(raw: Any) -> ReconciliationReport:
    """Convert a raw ReconciliationService result dict into a ReconciliationReport.

    Args:
        raw: Either a dict ``{"checks": [...]}`` or an existing ReconciliationReport.

    Returns:
        A populated ReconciliationReport instance.
    """
    if isinstance(raw, ReconciliationReport):
        return raw
    checks: list[dict[str, Any]] = raw.get("checks", []) if isinstance(raw, dict) else []
    if not checks:
        return ReconciliationReport(
            passed=True, row_count_match=True, column_match=True, diff_summary="no checks run"
        )
    failed = [c for c in checks if c.get("status") != "pass"]
    passed_checks = [c for c in checks if c.get("status") == "pass"]
    all_passed = len(failed) == 0
    row_ok = any(c.get("name") == "row_count" and c.get("status") == "pass" for c in checks)
    col_ok = any(c.get("name") == "columns" and c.get("status") == "pass" for c in checks)
    details = "; ".join(c.get("detail", "") for c in failed if c.get("detail"))
    diff = details or f"{len(passed_checks)}/{len(checks)} checks passed"
    return ReconciliationReport(
        passed=all_passed,
        row_count_match=row_ok,
        column_match=col_ok,
        diff_summary=diff,
    )


class BlockExecutor:
    """Execute assembled generated blocks through reconciliation.

    Each call assembles *generated_so_far* into a flat Python string and runs
    ReconciliationService against optional reference data files.  Returns a
    ``(passed, error_summary)`` tuple so callers can decide whether to retry.
    """

    def __init__(self) -> None:
        """Initialise BlockExecutor with shared service instances."""
        self._reconciler = ReconciliationService()
        self._codegen = CodeGenerator()

    async def run(
        self,
        generated_so_far: list[GeneratedBlock],
        context: JobContext,
        backend: Any,
        ref_csv_path: str,
        ref_sas7bdat_path: str,
    ) -> tuple[bool, str | None]:
        """Assemble and reconcile the current set of generated blocks.

        If both *ref_csv_path* and *ref_sas7bdat_path* are absent or empty,
        the check is a no-op and returns ``(True, None)``.

        Args:
            generated_so_far: All GeneratedBlock instances to assemble.
            context: Current job context (supplies resolved macro variables).
            backend: ComputeBackend instance used by ReconciliationService.
            ref_csv_path: Path to reference CSV, or empty string.
            ref_sas7bdat_path: Path to reference SAS7BDAT, or empty string.

        Returns:
            ``(True, None)`` when reconciliation passes or is skipped.
            ``(False, error_summary)`` when reconciliation fails.
        """
        if not ref_csv_path and not ref_sas7bdat_path:
            return (True, None)

        python_code = self._codegen.assemble_flat(
            generated_so_far, macro_vars=context.resolved_macros
        )

        try:
            raw = await asyncio.to_thread(
                self._reconciler.run,
                ref_csv_path,
                python_code,
                backend,
                ref_sas7bdat_path,
            )
        except Exception as exc:
            return (False, str(exc)[:200])

        report = _to_report(raw)
        if report.passed or not report.diff_summary:
            return (True, None)
        return (False, report.diff_summary[:200] if report.diff_summary else None)
