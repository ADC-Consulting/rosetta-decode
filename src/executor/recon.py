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

# SAS stores dates as days since this epoch
_SAS_EPOCH = pd.Timestamp("1960-01-01")


def _coerce_sas_date_columns(
    ref: pd.DataFrame, actual: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Align type mismatches between ref and actual before recon checks.

    Handles two cases:
    - ref=object, actual=numeric: ref looks like formatted dates → convert both
      to days-since-SAS-epoch floats.
    - ref=numeric, actual=object: actual looks like numeric strings (e.g. IDs
      cast to string by F61) → coerce actual to numeric for comparison.
    """
    ref = ref.copy()
    actual = actual.copy()
    for col in ref.columns:
        if col not in actual.columns:
            continue
        # Detect by "not numeric" rather than "is object": pandas >=2 infers a
        # dedicated StringDtype for text columns, for which is_object_dtype is
        # False. is_numeric_dtype is the version-robust discriminator.
        r_num = pd.api.types.is_numeric_dtype(ref[col])
        a_num = pd.api.types.is_numeric_dtype(actual[col])

        if not r_num and a_num:
            # ref=non-numeric, actual=numeric — is the text column dates in disguise?
            # Decide by the parseable fraction among NON-BLANK cells only: sparse
            # clinical date columns (first AE date, death date) are legitimately
            # mostly null, and blanks must not count as "not a date".
            ref_as_dt = pd.to_datetime(ref[col], errors="coerce")
            non_blank = ref[col].replace("", pd.NA).dropna()
            if len(non_blank) == 0:
                continue
            parseable = pd.to_datetime(non_blank, errors="coerce").notna().mean()
            if parseable < 0.8:
                continue
            actual_as_dt = pd.to_datetime(actual[col], unit="D", origin=_SAS_EPOCH, errors="coerce")
            ref[col] = (ref_as_dt - _SAS_EPOCH).dt.days.astype("float64")
            actual[col] = (actual_as_dt - _SAS_EPOCH).dt.days.astype("float64")
            logger.debug("recon: normalised SAS date column '%s' to days-since-1960", col)

        elif r_num and not a_num:
            # ref=numeric, actual=non-numeric — coerce actual to numeric if its
            # non-blank cells are predominantly numeric strings (e.g. F61 IDs).
            non_blank = actual[col].replace("", pd.NA).dropna()
            if len(non_blank) == 0:
                continue
            numeric_frac = pd.to_numeric(non_blank, errors="coerce").notna().mean()
            if numeric_frac < 0.8:
                continue
            actual[col] = pd.to_numeric(actual[col], errors="coerce")
            logger.debug("recon: coerced object column '%s' to numeric for comparison", col)

    return ref, actual


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
        except (KeyError, TypeError, ValueError, OverflowError):
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
        import pyreadstat  # type: ignore[import-untyped, unused-ignore]

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

    # Normalize column names to lowercase so SAS uppercase cols match Python lowercase
    ref_df.columns = ref_df.columns.str.lower()
    actual_df.columns = actual_df.columns.str.lower()

    logger.debug(
        "recon ref   rows=%d cols=%s dtypes=%s",
        len(ref_df),
        list(ref_df.columns),
        ref_df.dtypes.to_dict(),
    )
    logger.debug(
        "recon actual rows=%d cols=%s dtypes=%s",
        len(actual_df),
        list(actual_df.columns),
        actual_df.dtypes.to_dict(),
    )

    ref_df, actual_df = _coerce_sas_date_columns(ref_df, actual_df)

    return [
        _schema_parity(ref_df, actual_df),
        _row_count(ref_df, actual_df),
        _aggregate_parity(ref_df, actual_df),
    ]
