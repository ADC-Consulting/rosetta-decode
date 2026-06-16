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

# Maximum number of mismatched-row samples embedded in a row_hash_diff detail.
_ROW_DIFF_SAMPLE_CAP = 10

# A column qualifies as a join key only when its non-null values index rows
# (near-)uniquely.
_KEY_UNIQUENESS_THRESHOLD = 0.95

# A key component must be (near-)fully populated in BOTH frames. A column whose
# null fraction exceeds this tolerance is rejected — this is what disqualifies
# sparse clinical columns such as ``dthdtc`` (death date), which are null for
# almost every subject and therefore cannot align rows.
_KEY_MAX_NULL_FRACTION = 0.01

# Substrings / suffixes that mark a column NAME as identifier-like. Used only to
# RANK candidates — a name match never bypasses the null + uniqueness gates.
_ID_NAME_HINTS = ("usubjid", "subjid", "siteid", "subjectid", "patientid", "studyid")
_ID_NAME_SUFFIXES = ("id", "subjid", "seq", "num", "no")

# Upper bound on the cardinality of a column eligible for the COMPOSITE search.
_COMPOSITE_MAX_CARDINALITY = 0.95

# Largest composite-key arity attempted (pairs, then triples); bounds the search.
_COMPOSITE_MAX_ARITY = 3


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


def _null_fraction(frame: pd.DataFrame, col: str) -> float:
    """Return the fraction of null / blank cells in *frame[col]* (1.0 when empty)."""
    if len(frame) == 0:
        return 1.0
    series = frame[col].replace("", pd.NA) if frame[col].dtype == object else frame[col]
    return float(series.isna().mean())


def _passes_null_gate(ref: pd.DataFrame, actual: pd.DataFrame, col: str) -> bool:
    """A key component must be (near-)fully populated in BOTH frames."""
    return (
        _null_fraction(ref, col) <= _KEY_MAX_NULL_FRACTION
        and _null_fraction(actual, col) <= _KEY_MAX_NULL_FRACTION
    )


def _is_unique(ref: pd.DataFrame, cols: list[str]) -> bool:
    """Return True when the *cols* tuple is non-null and effectively unique in *ref*.

    Uniqueness is measured over non-null rows but required relative to the FULL
    row count, so a column unique only because most rows were dropped as null
    does not qualify (the null gate is enforced separately by callers).
    """
    non_null = ref[cols].dropna()
    if len(non_null) == 0:
        return False
    return non_null.drop_duplicates().shape[0] / len(ref) >= _KEY_UNIQUENESS_THRESHOLD


def _name_rank(col: str) -> int:
    """Rank a column NAME by identifier-likeness (lower = more identifier-like).

    Names are a preference/tiebreaker only — ranking never bypasses the null or
    uniqueness gates applied by :func:`_infer_join_keys`.
    """
    lowered = col.lower()
    if lowered in _ID_NAME_HINTS:
        return 0
    if any(hint in lowered for hint in _ID_NAME_HINTS):
        return 1
    if lowered.endswith(_ID_NAME_SUFFIXES):
        return 2
    return 3


def _ranked_candidates(ref: pd.DataFrame, actual: pd.DataFrame) -> list[str]:
    """Columns present in both frames that pass the null gate, id-name-ranked.

    Stable secondary ordering by original column position keeps the function
    deterministic (same inputs → same output).
    """
    common = [c for c in ref.columns if c in actual.columns]
    eligible = [c for c in common if _passes_null_gate(ref, actual, c)]
    return sorted(eligible, key=lambda c: (_name_rank(c), list(ref.columns).index(c)))


def _find_composite_key(ref: pd.DataFrame, candidates: list[str]) -> list[str]:
    """Search for the smallest non-null, unique composite key among *candidates*.

    Only low/medium-cardinality columns take part. Pairs are tried before
    triples; arity is capped at :data:`_COMPOSITE_MAX_ARITY` to bound the search.
    """
    import itertools

    row_count = len(ref)
    pool = [
        c for c in candidates if ref[c].dropna().nunique() / row_count <= _COMPOSITE_MAX_CARDINALITY
    ]
    for arity in range(2, _COMPOSITE_MAX_ARITY + 1):
        for combo in itertools.combinations(pool, arity):
            if _is_unique(ref, list(combo)):
                return list(combo)
    return []


def _infer_join_keys(ref: pd.DataFrame, actual: pd.DataFrame) -> list[str]:
    """Deterministically infer a validated join key for ``row_hash_diff``.

    Self-contained mirror of the worker copy (no worker import). Pure function:
    same inputs → same output. A column is a viable key component only when it is
    present in BOTH frames and is (near-)fully populated — the null gate
    (:data:`_KEY_MAX_NULL_FRACTION`) disqualifies sparse columns such as
    ``dthdtc`` regardless of their name. Resolution order:

    1. Single column — accept the highest id-name-ranked candidate that is
       effectively UNIQUE (:data:`_KEY_UNIQUENESS_THRESHOLD`) across all rows.
    2. Composite — search the smallest non-null, unique combination of
       low/medium-cardinality candidates (pairs, then triples; bounded by
       :data:`_COMPOSITE_MAX_ARITY`).
    3. Otherwise return ``[]`` so the caller falls back to positional comparison.

    Identifier-like names (``usubjid``, ``*subjid``, ``*id``, ``siteid`` …) are
    preferred only as a ranking tiebreaker; never accepted on name alone.

    Args:
        ref: The reference (SAS) frame.
        actual: The migrated (Python) frame.

    Returns:
        Ordered list of usable join-key column names, or ``[]``.
    """
    if len(ref) == 0 or not [c for c in ref.columns if c in actual.columns]:
        return []

    candidates = _ranked_candidates(ref, actual)
    if not candidates:
        logger.info("row_hash_diff: no usable join key inferred (no fully-populated common column)")
        return []

    for col in candidates:
        if _is_unique(ref, [col]):
            logger.debug("row_hash_diff: inferred single-column join key '%s'", col)
            return [col]

    composite = _find_composite_key(ref, candidates)
    if composite:
        logger.debug("row_hash_diff: inferred composite join key %s", composite)
        return composite

    logger.info("row_hash_diff: no usable join key inferred (no unique single or composite key)")
    return []


def _datetime_equivalent(ref_val: Any, act_val: Any) -> bool:
    """Return True when two non-numeric cells are the same instant in different formats.

    Conservative datetime-equivalence fallback used by :func:`_values_match`
    *only* after a direct comparison has already reported the cells as differing.
    Both sides must be non-numeric/string-like and BOTH must parse to a valid
    timestamp via :func:`pandas.to_datetime` (``errors="coerce"``); the cells are
    treated as equal only when the parsed timestamps are exactly equal. Two
    genuinely different dates (e.g. ``2025-06-10`` vs ``2025-06-11``) still differ.

    Pure and deterministic: no global state, same inputs → same result. Mirrors
    the date-parsing spirit of :func:`_coerce_sas_date_columns`.

    Args:
        ref_val: Reference cell value (already known to be non-numeric here).
        act_val: Actual cell value (already known to be non-numeric here).

    Returns:
        True iff both values parse to valid, equal timestamps.
    """
    ref_ts = pd.to_datetime(ref_val, errors="coerce")
    act_ts = pd.to_datetime(act_val, errors="coerce")
    if pd.isna(ref_ts) or pd.isna(act_ts):
        return False
    return bool(ref_ts == act_ts)


def _values_match(ref_val: Any, act_val: Any, float_tolerance: float) -> bool:
    """Return True when two cell values are equal within tolerance.

    Numeric pairs are compared within a relative *float_tolerance*; all other
    pairs by equality. Two nulls match. When a non-numeric pair compares unequal,
    a conservative datetime-equivalence fallback (:func:`_datetime_equivalent`)
    treats values that parse to the same timestamp as equal — collapsing
    date-vs-timestamp format differences (e.g. ``2025-06-10`` vs
    ``2025-06-10T00:00:00.000``) without masking real diffs.
    """
    ref_na = pd.isna(ref_val)
    act_na = pd.isna(act_val)
    if ref_na and act_na:
        return True
    if ref_na != act_na:
        return False
    ref_num = isinstance(ref_val, (int, float)) and not isinstance(ref_val, bool)
    act_num = isinstance(act_val, (int, float)) and not isinstance(act_val, bool)
    if ref_num and act_num:
        ref_f = float(ref_val)
        act_f = float(act_val)
        if ref_f == 0.0:
            return act_f == 0.0
        return abs(ref_f - act_f) / abs(ref_f) <= float_tolerance
    if bool(ref_val == act_val):
        return True
    # Both sides are non-numeric and differ textually — collapse equivalent
    # date/datetime strings expressed in different formats before flagging.
    if not ref_num and not act_num:
        return _datetime_equivalent(ref_val, act_val)
    return False


def _format_row_diff_detail(
    *,
    only_ref: int,
    only_actual: int,
    cell_diffs: list[str],
    join_keys: list[str],
    positional: bool,
) -> str:
    """Render a bounded human-readable detail string for row_hash_diff."""
    parts: list[str] = []
    if positional:
        parts.append("positional comparison (no usable join key)")
    else:
        parts.append(f"join_keys={join_keys}")
    if only_ref:
        parts.append(f"{only_ref} row(s) only in ref")
    if only_actual:
        parts.append(f"{only_actual} row(s) only in actual")
    if cell_diffs:
        sample = cell_diffs[:_ROW_DIFF_SAMPLE_CAP]
        more = len(cell_diffs) - len(sample)
        parts.append(f"{len(cell_diffs)} differing cell-group(s); sample: " + " | ".join(sample))
        if more > 0:
            parts.append(f"(+{more} more)")
    return "; ".join(parts)


def _compare_keyed(
    ref: pd.DataFrame, actual: pd.DataFrame, join_keys: list[str], float_tolerance: float
) -> dict[str, Any]:
    """Outer-join on *join_keys* and compare non-key columns row-by-row.

    A non-unique / null explicit key would fan the outer join out into a
    near-cartesian product and silently misalign rows. The inferred keys are
    pre-validated; an explicit key is not overridden, so its quality is checked
    here and surfaced as a warning rather than silently misaligning.
    """
    key_warning = _key_quality_warning(ref, actual, join_keys)
    if key_warning:
        logger.warning("row_hash_diff: %s", key_warning)
    merged = ref.merge(
        actual, on=join_keys, how="outer", suffixes=("__ref", "__act"), indicator=True
    )
    only_ref = int((merged["_merge"] == "left_only").sum())
    only_actual = int((merged["_merge"] == "right_only").sum())
    both = merged[merged["_merge"] == "both"]

    value_cols = [c for c in ref.columns if c not in join_keys and c in actual.columns]
    cell_diffs: list[str] = []
    for _, row in both.iterrows():
        key_repr = ", ".join(f"{k}={row[k]!r}" for k in join_keys)
        differing: list[str] = []
        for col in value_cols:
            ref_val = row[f"{col}__ref"]
            act_val = row[f"{col}__act"]
            if _values_match(ref_val, act_val, float_tolerance):
                continue
            differing.append(f"{col}(ref={ref_val!r},actual={act_val!r})")
        if differing:
            cell_diffs.append(f"[{key_repr}] " + ", ".join(differing))
        if len(cell_diffs) > _ROW_DIFF_SAMPLE_CAP:
            break

    passed = only_ref == 0 and only_actual == 0 and not cell_diffs
    detail = (
        ""
        if passed
        else _format_row_diff_detail(
            only_ref=only_ref,
            only_actual=only_actual,
            cell_diffs=cell_diffs,
            join_keys=join_keys,
            positional=False,
        )
    )
    if key_warning:
        # Surface a non-unique / null explicit key even when the diff otherwise
        # passes, so a fan-out cartesian join is never silently accepted.
        detail = f"{key_warning}; {detail}" if detail else key_warning
        result = _check_result("row_hash_diff", passed=passed, detail=detail)
        result["key_warning"] = key_warning
        return result
    return _check_result("row_hash_diff", passed=passed, detail=detail)


def _key_quality_warning(ref: pd.DataFrame, actual: pd.DataFrame, join_keys: list[str]) -> str:
    """Return a warning string when *join_keys* are null-prone or non-unique, else ``""``.

    Validates an EXPLICITLY configured key without overriding it: a mostly-null
    or non-unique configured key would fan the outer join out into a
    near-cartesian product and silently misalign rows, so its quality is noted.
    """
    issues: list[str] = []
    for col in join_keys:
        if _null_fraction(ref, col) > _KEY_MAX_NULL_FRACTION:
            issues.append(f"'{col}' is mostly-null in ref")
        elif _null_fraction(actual, col) > _KEY_MAX_NULL_FRACTION:
            issues.append(f"'{col}' is mostly-null in actual")
    if join_keys and not _is_unique(ref, join_keys):
        issues.append(f"key {join_keys} is non-unique in ref")
    if not issues:
        return ""
    return "configured join key is low quality (" + "; ".join(issues) + ")"


def _compare_positional(
    ref: pd.DataFrame, actual: pd.DataFrame, float_tolerance: float
) -> dict[str, Any]:
    """Stable-sort both frames by all columns and compare row-aligned."""
    common = [c for c in ref.columns if c in actual.columns]
    if not common:
        return _check_result("row_hash_diff", passed=True)

    # Stable-sort by all common columns. Mixed-type (object) columns are not
    # sortable in pandas; fall back to the original row order rather than crash.
    try:
        ref_sorted = ref[common].sort_values(by=common, kind="stable").reset_index(drop=True)
        act_sorted = actual[common].sort_values(by=common, kind="stable").reset_index(drop=True)
    except TypeError:
        ref_sorted = ref[common].reset_index(drop=True)
        act_sorted = actual[common].reset_index(drop=True)

    cell_diffs: list[str] = []
    for idx in range(min(len(ref_sorted), len(act_sorted))):
        differing: list[str] = []
        for col in common:
            ref_val = ref_sorted.at[idx, col]
            act_val = act_sorted.at[idx, col]
            if _values_match(ref_val, act_val, float_tolerance):
                continue
            differing.append(f"{col}(ref={ref_val!r},actual={act_val!r})")
        if differing:
            cell_diffs.append(f"[row {idx}] " + ", ".join(differing))
        if len(cell_diffs) > _ROW_DIFF_SAMPLE_CAP:
            break

    only_ref = max(0, len(ref_sorted) - len(act_sorted))
    only_actual = max(0, len(act_sorted) - len(ref_sorted))
    passed = only_ref == 0 and only_actual == 0 and not cell_diffs
    detail = (
        ""
        if passed
        else _format_row_diff_detail(
            only_ref=only_ref,
            only_actual=only_actual,
            cell_diffs=cell_diffs,
            join_keys=[],
            positional=True,
        )
    )
    return _check_result("row_hash_diff", passed=passed, detail=detail)


def _row_hash_diff(
    ref: pd.DataFrame,
    actual: pd.DataFrame,
    *,
    join_keys: list[str],
    float_tolerance: float,
) -> dict[str, Any]:
    """Record-level diff: compare reference and actual rows value-by-value.

    Resolves keys: explicit *join_keys* (when present in both frames) →
    :func:`_infer_join_keys` → positional fallback. Self-contained mirror of the
    worker copy.
    """
    resolved = [k for k in join_keys if k in ref.columns and k in actual.columns]
    if join_keys and not resolved:
        logger.warning("row_hash_diff: configured join_keys %s not found; inferring", join_keys)
    if not resolved:
        resolved = _infer_join_keys(ref, actual)

    if not resolved:
        return _compare_positional(ref, actual, float_tolerance)
    return _compare_keyed(ref, actual, resolved, float_tolerance)


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
    recon_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run the reconciliation checks against a reference dataset.

    Args:
        result_json: DataFrame rows produced by the executed code (from runner.py).
        ref_csv_path: Path to the reference CSV (may be empty string).
        ref_sas7bdat_path: Path to the reference .sas7bdat (may be empty string).
        recon_config: Optional record-level config (plain dict from the wire);
            ``join_keys`` (lowercased) and ``float_tolerance`` are resolved with
            the same defaults as the worker ``ReconConfig``.

    Returns:
        List of check result dicts: ``[{"name", "status", "detail?"}, ...]``.
        Returns a single execution-failure check on load error.
    """
    if not ref_csv_path and not ref_sas7bdat_path:
        return []

    # Resolve record-level config (executor stays dict-based — no shared model).
    cfg = recon_config or {}
    join_keys = [str(k).strip().lower() for k in (cfg.get("join_keys") or []) if str(k).strip()]
    try:
        tolerance_raw = cfg.get("float_tolerance")
        float_tolerance = float(tolerance_raw) if tolerance_raw is not None else _AGGREGATE_RTOL
    except (TypeError, ValueError):
        float_tolerance = _AGGREGATE_RTOL

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
        _row_hash_diff(ref_df, actual_df, join_keys=join_keys, float_tolerance=float_tolerance),
    ]
