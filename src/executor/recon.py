"""Reconciliation checks for the executor microservice.

Mirrors the three checks in src/worker/validation/reconciliation.py but
operates on plain dicts (from JSON) and local file paths.  This module is
intentionally self-contained — it must NOT import from src/worker because
executor runs in a separate container.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Relative tolerance for aggregate comparisons (0.001 = 0.1 %)
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


def _load_reference(ref_csv_path: str, ref_sas7bdat_path: str) -> pd.DataFrame:
    """Load the reference dataset from sas7bdat or csv (sas7bdat takes priority).

    Args:
        ref_csv_path: Path to a CSV reference file (may be empty string).
        ref_sas7bdat_path: Path to a .sas7bdat reference file (may be empty string).

    Returns:
        Loaded DataFrame.

    Raises:
        ValueError: If neither path is supplied.
        Exception: Propagated from pandas / pyreadstat on load failure.
    """
    if ref_sas7bdat_path:
        import pyreadstat  # type: ignore[import-untyped]

        df, _ = pyreadstat.read_sas7bdat(ref_sas7bdat_path)
        return pd.DataFrame(df)
    if ref_csv_path:
        return pd.read_csv(ref_csv_path)
    raise ValueError("Neither ref_csv_path nor ref_sas7bdat_path was supplied.")


def run_recon(
    result_json: list[dict[str, Any]],
    ref_csv_path: str,
    ref_sas7bdat_path: str,
) -> list[dict[str, Any]]:
    """Run the three reconciliation checks against a reference dataset.

    Args:
        result_json: DataFrame rows produced by the executed code (from runner.py).
        ref_csv_path: Path to the reference CSV (may be empty string).
        ref_sas7bdat_path: Path to the reference .sas7bdat (may be empty string).

    Returns:
        List of check result dicts: ``[{"name", "status", "detail?"}, ...]``.
        Returns a single execution-failure check on load error.
    """
    if not ref_csv_path and not ref_sas7bdat_path:
        return []

    try:
        ref_df = _load_reference(ref_csv_path, ref_sas7bdat_path)
    except Exception as exc:
        logger.warning("Recon: failed to load reference data: %s", exc)
        return [_check_result("execution", passed=False, detail=str(exc))]

    actual_df = pd.DataFrame(result_json)

    return [
        _schema_parity(ref_df, actual_df),
        _row_count(ref_df, actual_df),
        _aggregate_parity(ref_df, actual_df),
    ]
