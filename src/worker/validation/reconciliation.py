"""ReconciliationService — validates generated Python output against a reference CSV.

Runs three checks in sequence:
1. schema_parity   — column names and dtypes match (with numeric coercion tolerance)
2. row_count       — same number of rows
3. aggregate_parity — SUM of every numeric column matches within a relative tolerance

Each check produces a structured result dict compatible with the ``report`` JSONB
field on the ``jobs`` table:
    { "name": str, "status": "pass" | "fail", "detail": str }  # detail only on fail
"""

from __future__ import annotations

import asyncio
import logging
import textwrap
import traceback
from typing import Any, cast

import httpx
import pandas as pd
from src.worker.compute.base import ComputeBackend
from src.worker.core.config import worker_settings

logger = logging.getLogger(__name__)

# Relative tolerance for aggregate comparisons (0.001 = 0.1%)
_AGGREGATE_RTOL = 0.001


def _check_result(name: str, *, passed: bool, detail: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {"name": name, "status": "pass" if passed else "fail"}
    if not passed and detail:
        result["detail"] = detail
    return result


def _schema_parity(ref: pd.DataFrame, actual: pd.DataFrame) -> dict[str, Any]:
    """Column names must match (order-insensitive); numeric cols must be numeric."""
    ref_cols = sorted(ref.columns.tolist())
    actual_cols = sorted(actual.columns.tolist())
    if ref_cols != actual_cols:
        missing = set(ref_cols) - set(actual_cols)
        extra = set(actual_cols) - set(ref_cols)
        detail = f"missing={sorted(missing)}, extra={sorted(extra)}"
        return _check_result("schema_parity", passed=False, detail=detail)

    mismatches: list[str] = []
    for col in ref.columns:
        r_numeric = pd.api.types.is_numeric_dtype(ref[col])
        a_numeric = pd.api.types.is_numeric_dtype(actual[col])
        if r_numeric != a_numeric:
            mismatches.append(
                f"{col}: ref={'numeric' if r_numeric else 'object'}, "
                f"actual={'numeric' if a_numeric else 'object'}"
            )
    if mismatches:
        return _check_result("schema_parity", passed=False, detail="; ".join(mismatches))

    return _check_result("schema_parity", passed=True)


def _row_count(ref: pd.DataFrame, actual: pd.DataFrame) -> dict[str, Any]:
    """Row counts must match exactly."""
    if len(ref) != len(actual):
        detail = f"ref={len(ref)}, actual={len(actual)}"
        return _check_result("row_count", passed=False, detail=detail)
    return _check_result("row_count", passed=True)


def _aggregate_parity(ref: pd.DataFrame, actual: pd.DataFrame) -> dict[str, Any]:
    """SUM of each numeric column must match within _AGGREGATE_RTOL."""
    numeric_cols = [c for c in ref.columns if pd.api.types.is_numeric_dtype(ref[c])]
    if not numeric_cols:
        return _check_result("aggregate_parity", passed=True)

    mismatches: list[str] = []
    for col in numeric_cols:
        ref_sum = float(ref[col].sum())
        try:
            actual_sum = float(actual[col].sum())
        except (KeyError, TypeError):
            mismatches.append(f"{col}: missing in actual")
            continue
        if ref_sum == 0.0:
            if actual_sum != 0.0:
                mismatches.append(f"{col}: ref=0, actual={actual_sum}")
        else:
            rel_diff = abs(ref_sum - actual_sum) / abs(ref_sum)
            if rel_diff > _AGGREGATE_RTOL:
                mismatches.append(
                    f"{col}: ref_sum={ref_sum:.4f}, actual_sum={actual_sum:.4f}, "
                    f"rel_diff={rel_diff:.6f}"
                )

    if mismatches:
        return _check_result("aggregate_parity", passed=False, detail="; ".join(mismatches))
    return _check_result("aggregate_parity", passed=True)


class ReconciliationService:
    """Run post-migration checks comparing generated output to a reference CSV."""

    def run(
        self,
        ref_csv_path: str,
        python_code: str,
        backend: ComputeBackend,
        ref_sas7bdat_path: str = "",
    ) -> dict[str, Any]:
        """Execute all reconciliation checks and return a structured report.

        The *python_code* is exec'd in a sandboxed namespace.  The last
        DataFrame assigned to a variable named ``result`` (or the last
        DataFrame-valued local) is taken as the pipeline output.

        Reference data is resolved in priority order: sas7bdat > csv > none.
        When no reference path is supplied, reconciliation is skipped.

        Args:
            ref_csv_path: Path to the reference CSV produced by the original SAS run.
            python_code: Generated Python pipeline source (from CodeGenerator).
            backend: The ComputeBackend to inject into the pipeline namespace.
            ref_sas7bdat_path: Optional path to a .sas7bdat reference dataset.

        Returns:
            Report dict: ``{ "checks": [ { "name", "status", "detail?" }, … ] }``
        """
        checks: list[dict[str, Any]] = []

        if not ref_sas7bdat_path and not ref_csv_path:
            # No reference data supplied — skip reconciliation entirely
            return {"checks": checks}

        try:
            actual_df = self._exec_pipeline(python_code, backend)
        except Exception:
            error_detail = textwrap.shorten(traceback.format_exc(), width=300)
            logger.warning("Reconciliation execution error: %s", error_detail)
            checks.append(_check_result("execution", passed=False, detail=error_detail))
            return {"checks": checks}

        try:
            if ref_sas7bdat_path:
                ref_df = cast(pd.DataFrame, backend.read_sas7bdat(ref_sas7bdat_path))
            else:
                ref_df = cast(pd.DataFrame, backend.read_csv(ref_csv_path))
        except Exception:
            error_detail = textwrap.shorten(traceback.format_exc(), width=300)
            logger.warning("Reconciliation reference load error: %s", error_detail)
            checks.append(_check_result("execution", passed=False, detail=error_detail))
            return {"checks": checks}

        checks.append(_schema_parity(ref_df, actual_df))
        checks.append(_row_count(ref_df, actual_df))
        checks.append(_aggregate_parity(ref_df, actual_df))
        return {"checks": checks}

    @staticmethod
    def _exec_pipeline(python_code: str, backend: ComputeBackend) -> pd.DataFrame:
        """Execute *python_code* and extract the pipeline output DataFrame.

        The generated code runs with ``backend`` injected as a local.  The
        last variable assigned a DataFrame value is returned as the result.

        Args:
            python_code: Python source string from CodeGenerator.
            backend: ComputeBackend instance available to the generated code.

        Returns:
            The output DataFrame produced by the pipeline.

        Raises:
            ValueError: If no DataFrame is found in the execution namespace.
        """
        namespace: dict[str, Any] = {"backend": backend, "pd": pd}
        exec(python_code, namespace)

        # Prefer an explicit "result" variable; fall back to last DataFrame found.
        if "result" in namespace and isinstance(namespace["result"], pd.DataFrame):
            return namespace["result"]

        dataframes = [v for v in namespace.values() if isinstance(v, pd.DataFrame)]
        if not dataframes:
            raise ValueError(
                "Generated pipeline produced no pandas DataFrame in its namespace. "
                "Ensure the final output is assigned to a variable named 'result'."
            )
        return dataframes[-1]


class RemoteReconciliationService:
    """Delegate reconciliation to the executor microservice over HTTP.

    Sends the generated Python code to the executor's ``POST /execute`` endpoint
    and returns a ``{"checks": [...]}`` dict in the same format as
    :class:`ReconciliationService`.  Falls back to an empty checks list when the
    executor is unreachable.
    """

    def _post_execute(
        self,
        python_code: str,
        ref_csv_path: str,
        ref_sas7bdat_path: str,
    ) -> dict[str, Any]:
        """Call the executor synchronously (intended for asyncio.to_thread use).

        Args:
            python_code: Python source to execute remotely.
            ref_csv_path: Path to reference CSV (may be empty string).
            ref_sas7bdat_path: Path to reference .sas7bdat (may be empty string).

        Returns:
            Parsed JSON response body from the executor.
        """
        url = f"{worker_settings.executor_url}/execute"
        payload = {
            "code": python_code,
            "ref_csv_path": ref_csv_path,
            "ref_sas7bdat_path": ref_sas7bdat_path,
        }
        with httpx.Client(timeout=120) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            return dict(response.json())

    async def run(
        self,
        ref_csv_path: str,
        python_code: str,
        backend: ComputeBackend,
        ref_sas7bdat_path: str = "",
    ) -> dict[str, Any]:
        """Post the generated code to the executor and return reconciliation results.

        Signature matches :meth:`ReconciliationService.run` so callers can swap
        implementations without changing call sites.

        Args:
            ref_csv_path: Path to reference CSV (may be empty string).
            python_code: Generated Python pipeline source.
            backend: Unused — kept for interface parity with ReconciliationService.
            ref_sas7bdat_path: Optional path to reference .sas7bdat.

        Returns:
            ``{"checks": [...]}`` dict, or ``{"checks": []}`` on executor failure.
        """
        if not ref_csv_path and not ref_sas7bdat_path:
            return {"checks": []}

        try:
            raw = await asyncio.to_thread(
                self._post_execute,
                python_code,
                ref_csv_path,
                ref_sas7bdat_path,
            )
            checks = raw.get("checks") or []
            return {"checks": checks}
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            logger.warning("RemoteReconciliationService: executor unreachable: %s", exc)
            return {"checks": []}
        except Exception as exc:
            logger.warning("RemoteReconciliationService: unexpected error: %s", exc)
            return {"checks": []}
