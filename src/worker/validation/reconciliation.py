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
import re
from typing import Any, cast

import httpx
import pandas as pd
from pydantic import BaseModel, Field
from src.worker.compute.base import ComputeBackend
from src.worker.core.config import worker_settings

logger = logging.getLogger(__name__)

# Relative tolerance for aggregate comparisons (0.001 = 0.1%)
_AGGREGATE_RTOL = 0.001

# SAS stores dates as days since this epoch
_SAS_EPOCH = pd.Timestamp("1960-01-01")

# Maximum number of mismatched-row samples embedded in a row_hash_diff detail
# string — keeps the persisted JSON payload bounded for wide / large frames.
_ROW_DIFF_SAMPLE_CAP = 10

# A column is usable as a join key only when its non-null values index rows
# (near-)uniquely; below this fraction the column is too coarse to align rows.
_KEY_UNIQUENESS_THRESHOLD = 0.95

# A key component must be (near-)fully populated in BOTH frames. A column whose
# null fraction exceeds this tolerance is rejected — this is what disqualifies
# sparse clinical columns such as ``dthdtc`` (death date), which are null for
# almost every subject and therefore cannot align rows.
_KEY_MAX_NULL_FRACTION = 0.01

# Substrings that mark a column NAME as identifier-like. Used only to RANK /
# prefer candidates — a name match never bypasses the null + uniqueness gates.
_ID_NAME_HINTS = ("usubjid", "subjid", "siteid", "subjectid", "patientid", "studyid")
_ID_NAME_SUFFIXES = ("id", "subjid", "seq", "num", "no")

# Upper bound on the cardinality (distinct non-null values relative to row count)
# of a column eligible to take part in a COMPOSITE key search. Columns that are
# almost as unique as the row count (e.g. free-text) add no grouping value and
# blow up the combinatorics, so only low/medium-cardinality columns are paired.
_COMPOSITE_MAX_CARDINALITY = 0.95

# Bound on the composite-key search: we try every pair, then every triple, of
# the ranked candidate columns and stop at the first non-null unique tuple.
# Triples are the largest combination attempted (clinical keys are siteid+subjid
# or usubjid; a 3-part key covers studyid+siteid+subjid). Higher arities are not
# searched to keep the cost bounded at O(n^3) in the candidate count.
_COMPOSITE_MAX_ARITY = 3


class ReconConfig(BaseModel):
    """Typed configuration for record-level reconciliation.

    Attributes:
        join_keys: Column names (lowercased) used to align reference and actual
            rows in the ``row_hash_diff`` check. Empty → keys are auto-inferred.
        float_tolerance: Relative tolerance applied when comparing numeric
            non-key columns row-by-row (mirrors the aggregate-parity idiom).
        resolve_key_with_llm: When True, a failed ``row_hash_diff`` (all other
            checks passing) triggers the per-block LLM join-key resolution loop
            (F15). The LLM proposes the correct business key; the worker re-runs
            only the comparison in-process. The LLM never touches generated code.
        max_key_attempts: Upper bound on LLM key-resolution attempts per block,
            mirroring the per-block translation attempt budget.
    """

    join_keys: list[str] = Field(default_factory=list)
    float_tolerance: float = _AGGREGATE_RTOL
    resolve_key_with_llm: bool = True
    max_key_attempts: int = 3

    @classmethod
    def from_metadata(cls, raw: dict[str, Any] | None) -> ReconConfig:
        """Build a ReconConfig from an untrusted metadata dict.

        Tolerates ``None`` and partial dicts (missing or malformed keys fall
        back to defaults) and lowercases ``join_keys`` to match the
        column-casing convention used throughout reconciliation.

        Args:
            raw: Parsed ``__recon_config__`` metadata, or ``None`` when absent.

        Returns:
            A populated ReconConfig (defaults when *raw* is empty/invalid).
        """
        if not raw or not isinstance(raw, dict):
            return cls()
        keys_raw = raw.get("join_keys") or []
        join_keys = [str(k).strip().lower() for k in keys_raw if str(k).strip()]
        tolerance = raw.get("float_tolerance")
        try:
            float_tolerance = float(tolerance) if tolerance is not None else _AGGREGATE_RTOL
        except (TypeError, ValueError):
            float_tolerance = _AGGREGATE_RTOL
        resolve_raw = raw.get("resolve_key_with_llm")
        resolve_key_with_llm = bool(resolve_raw) if resolve_raw is not None else True
        attempts_raw = raw.get("max_key_attempts")
        try:
            max_key_attempts = int(attempts_raw) if attempts_raw is not None else 3
        except (TypeError, ValueError):
            max_key_attempts = 3
        return cls(
            join_keys=join_keys,
            float_tolerance=float_tolerance,
            resolve_key_with_llm=resolve_key_with_llm,
            max_key_attempts=max_key_attempts,
        )


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


_spark_session: Any = None


def _get_spark() -> Any:
    """Return a lazily-created local SparkSession, or None if pyspark is not installed."""
    global _spark_session
    if _spark_session is None:
        try:
            logging.getLogger("py4j").setLevel(logging.WARNING)
            logging.getLogger("py4j.clientserver").setLevel(logging.WARNING)
            from pyspark.sql import SparkSession  # type: ignore[import-not-found]

            _spark_session = (
                SparkSession.builder.master("local[*]")
                .appName("rosetta-reconciliation")
                .config("spark.ui.enabled", "false")
                .config("spark.sql.shuffle.partitions", "4")
                .getOrCreate()
            )
            _spark_session.sparkContext.setLogLevel("ERROR")
            logger.info("Local SparkSession initialised for reconciliation")
        except ImportError:
            return None
    return _spark_session


def _to_pandas(obj: Any) -> pd.DataFrame | None:
    """Convert a Spark DataFrame to pandas, or return as-is if already pandas."""
    try:
        from pyspark.sql import DataFrame as SparkDataFrame

        if isinstance(obj, SparkDataFrame):
            result: pd.DataFrame = obj.toPandas()
            return result
    except ImportError:
        pass
    if isinstance(obj, pd.DataFrame):
        return obj
    return None


def _add_column_to_spark_df(df: Any, col_name: str, spark: Any) -> Any:
    """Return *df* with *col_name* added as a null StringType column."""
    try:
        from pyspark.sql import functions as F  # type: ignore[import-not-found]  # noqa: N812
        from pyspark.sql.types import StringType  # type: ignore[import-not-found]

        return df.withColumn(col_name, F.lit(None).cast(StringType()))
    except Exception:
        return df


def qualify_ambiguous_column(code: str, err_str: str) -> str | None:
    """Rewrite bare ``F.col("<col>")`` refs to the first alias-qualified candidate.

    Parses a Spark ``AMBIGUOUS_REFERENCE`` error string to learn the ambiguous
    column name and the first alias-qualified candidate from the message's
    ``could be: [`a`.`col`, ...]`` list. It then rewrites every bare
    ``F.col("<col>")`` / ``F.col('<col>')`` in *code* that is NOT already
    alias-qualified into ``F.col("<alias>.<col>")``.

    This deterministically self-heals generated PySpark where a condition-join
    left two columns of the same name (see SHARED_TRANSLATION_RULES §5).

    Args:
        code: The generated Python source to patch.
        err_str: The Spark exception string (or stderr) to parse.

    Returns:
        The patched code, or ``None`` if no ``AMBIGUOUS_REFERENCE`` / alias
        candidate could be parsed (so the caller can stop / re-raise).
    """
    if "AMBIGUOUS_REFERENCE" not in err_str:
        return None
    ref_match = re.search(r"Reference `(\w+)` is ambiguous", err_str)
    if ref_match is None:
        return None
    col = ref_match.group(1)
    # Learn the first alias from the candidate list: could be: [`a`.`usubjid`, ...]
    alias_match = re.search(r"could be:\s*\[`(\w+)`\.`" + re.escape(col) + r"`", err_str)
    if alias_match is None:
        return None
    alias = alias_match.group(1)

    # Replace bare F.col("col") / F.col('col') only — alias-qualified refs such as
    # F.col("a.col") contain a dot and are not matched by this pattern.
    pattern = re.compile(r'F\.col\(\s*(["\'])' + re.escape(col) + r"\1\s*\)")
    replacement = f'F.col("{alias}.{col}")'
    patched, n_subs = pattern.subn(replacement, code)
    if n_subs == 0:
        return None
    logger.warning(
        "recon: AMBIGUOUS_REFERENCE on '%s' — qualified %d bare ref(s) with alias '%s'",
        col,
        n_subs,
        alias,
    )
    return patched


def _safe_exec(code: str, ns: dict[str, Any]) -> None:
    """Exec *code* in *ns*, auto-injecting stubs for undefined names/columns.

    Retries up to 20 times. On each attempt:
    - NameError → inject an empty DataFrame for the missing name.
    - Spark AnalysisException (unresolved column) → find which DataFrame in the
      namespace was last assigned and add the missing column to it so the next
      exec attempt can proceed.
    - Spark AMBIGUOUS_REFERENCE → rewrite the code string in place, alias-qualifying
      bare ``F.col("<col>")`` refs with the first candidate alias from the message,
      and re-exec the patched code on the next iteration.

    Args:
        code: Python source to execute.
        ns: Execution namespace (mutated in place).
    """
    current_code = code
    for _ in range(20):
        try:
            exec(current_code, ns)
            return
        except NameError as exc:
            match = re.search(r"name '(\w+)' is not defined", str(exc))
            if not match:
                raise
            missing_name = match.group(1)
            spark = ns.get("spark")
            if spark is not None:
                try:
                    ns[missing_name] = spark.createDataFrame([], schema="")
                except Exception:
                    ns[missing_name] = spark.createDataFrame(pd.DataFrame())
            else:
                ns[missing_name] = pd.DataFrame()
        except Exception as exc:
            err_str = str(exc)
            # Spark AMBIGUOUS_REFERENCE — patch the code string, not the namespace.
            if "AMBIGUOUS_REFERENCE" in err_str:
                patched = qualify_ambiguous_column(current_code, err_str)
                if patched is None or patched == current_code:
                    raise
                current_code = patched
                continue
            # Spark AnalysisException: unresolved column — patch the offending DF stub
            col_match = re.search(
                r"UNRESOLVED_COLUMN[^`]*`(\w+)`|"
                r"cannot be resolved.*name `(\w+)`|"
                r"parameter with name `(\w+)`",
                err_str,
            )
            if col_match is None:
                raise
            missing_col = next(g for g in col_match.groups() if g)
            spark = ns.get("spark")
            if spark is None:
                raise
            # Add the missing column to every Spark DataFrame stub in the namespace
            try:
                from pyspark.sql import DataFrame as SparkDF  # type: ignore[import-not-found]

                patched_df = False
                for k, v in list(ns.items()):
                    if isinstance(v, SparkDF):
                        col_names = [f.name for f in v.schema.fields]
                        if missing_col not in col_names:
                            ns[k] = _add_column_to_spark_df(v, missing_col, spark)
                            patched_df = True
                if not patched_df:
                    raise
            except ImportError:
                raise
    exec(current_code, ns)  # final attempt — let it raise


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
    """Return the fraction of null / blank cells in *frame[col]* (0.0 when empty).

    Empty and whitespace-only strings count as null: SAS char blanks arrive as
    ``""`` and cannot align rows. The blank check is applied to any non-numeric
    dtype (pandas >=2 may infer ``StringDtype`` rather than ``object`` for text),
    mirroring the ``.replace("", pd.NA)`` blank-detection idiom used elsewhere.
    """
    if len(frame) == 0:
        return 1.0
    series = frame[col]
    if not pd.api.types.is_numeric_dtype(series):
        stripped = series.astype("object").map(
            lambda v: pd.NA if isinstance(v, str) and v.strip() == "" else v
        )
        return float(stripped.isna().mean())
    return float(series.isna().mean())


def _passes_null_gate(ref: pd.DataFrame, actual: pd.DataFrame, col: str) -> bool:
    """A key component must be (near-)fully populated in BOTH frames."""
    return (
        _null_fraction(ref, col) <= _KEY_MAX_NULL_FRACTION
        and _null_fraction(actual, col) <= _KEY_MAX_NULL_FRACTION
    )


def _is_unique(
    ref: pd.DataFrame, cols: list[str], threshold: float = _KEY_UNIQUENESS_THRESHOLD
) -> bool:
    """Return True when the *cols* tuple is non-null and unique in *ref* at *threshold*.

    Uniqueness is measured over non-null rows but required relative to the FULL
    row count, so a column that is unique only because most rows were dropped as
    null does not qualify (the null gate is enforced separately by callers).

    Args:
        ref: The frame to test.
        cols: Candidate key columns.
        threshold: Minimum distinct-non-null / total-row fraction required.
            Defaults to :data:`_KEY_UNIQUENESS_THRESHOLD` (0.95) so the
            deterministic ``_infer_join_keys`` path is byte-identical; the
            LLM-proposed-key validator passes ``1.0`` for exact uniqueness.

    Returns:
        True when the tuple meets the uniqueness threshold over non-null rows.
    """
    non_null = ref[cols].dropna()
    if len(non_null) == 0:
        return False
    return non_null.drop_duplicates().shape[0] / len(ref) >= threshold


def validate_proposed_key(ref: pd.DataFrame, actual: pd.DataFrame, proposed: list[str]) -> bool:
    """Return True iff *proposed* is a sound exact join key for BOTH frames.

    Pure function (no LLM, no global state). Stricter than the 0.95 inference
    gate — used to validate an LLM-proposed key before the in-process
    re-comparison (F15). A proposal is accepted only when, for every column:

    1. the column exists in BOTH ``ref`` and ``actual``,
    2. the tuple is EXACTLY unique (``threshold=1.0``) in BOTH frames, so the
       outer join cannot fan out on either side, and
    3. the tuple has zero nulls in BOTH frames.

    Args:
        ref: The reference (SAS) frame (columns already lowercased).
        actual: The migrated (Python) frame (columns already lowercased).
        proposed: Candidate key columns (already lowercased).

    Returns:
        True when *proposed* is a non-null, exactly-unique key in both frames.
    """
    if not proposed:
        return False
    for col in proposed:
        if col not in ref.columns or col not in actual.columns:
            return False
    # Zero nulls in both frames (blank strings count as null via _null_fraction).
    for col in proposed:
        if _null_fraction(ref, col) > 0.0 or _null_fraction(actual, col) > 0.0:
            return False
    # Exact uniqueness on BOTH sides — _is_unique only checked ref historically.
    return _is_unique(ref, proposed, threshold=1.0) and _is_unique(actual, proposed, threshold=1.0)


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

    Only low/medium-cardinality columns take part (a column already nearly as
    unique as the row count adds nothing and would have qualified as a single
    key). Pairs are tried before triples; arity is capped at
    :data:`_COMPOSITE_MAX_ARITY` to keep the search bounded.
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

    Pure function (no LLM, no global state): same inputs → same output. A column
    is only a viable key component when it is present in BOTH frames and is
    (near-)fully populated — the null gate (:data:`_KEY_MAX_NULL_FRACTION`)
    disqualifies sparse columns such as ``dthdtc`` regardless of their name.
    Resolution order:

    1. Single column — accept the highest id-name-ranked candidate that is
       effectively UNIQUE (:data:`_KEY_UNIQUENESS_THRESHOLD`) across all rows.
    2. Composite — if no single column qualifies, search the smallest non-null,
       unique combination of low/medium-cardinality candidates (pairs, then
       triples; bounded by :data:`_COMPOSITE_MAX_ARITY`).
    3. Otherwise return ``[]`` so the caller falls back to positional comparison.

    Identifier-like names (``usubjid``, ``*subjid``, ``*id``, ``siteid`` …) are
    preferred only as a ranking tiebreaker; a name match still has to pass the
    null and uniqueness gates and is never accepted on its name alone.

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

    When the supplied key is non-unique or contains nulls in either frame, the
    outer join can fan out (cartesian within key groups) and misalign rows. The
    caller's inferred keys are pre-validated, but an explicitly configured key is
    not overridden — so its quality is checked here and surfaced as a warning and
    a ``key_warning`` prefix in the detail rather than silently misaligning.
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

    Used to validate an EXPLICITLY configured key without overriding it: a
    mostly-null or non-unique configured key would fan the outer join out into a
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

    Numeric pairs are compared within a relative *float_tolerance* (mirroring
    :func:`_aggregate_parity`); all other pairs by equality. Two nulls match.
    When a non-numeric pair compares unequal, a conservative datetime-equivalence
    fallback (:func:`_datetime_equivalent`) treats values that parse to the same
    timestamp as equal — collapsing date-vs-timestamp format differences (e.g.
    ``2025-06-10`` vs ``2025-06-10T00:00:00.000``) without masking real diffs.
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


def _row_hash_diff(
    ref: pd.DataFrame,
    actual: pd.DataFrame,
    *,
    join_keys: list[str],
    float_tolerance: float,
) -> dict[str, Any]:
    """Record-level diff: compare reference and actual rows value-by-value.

    Resolves keys in priority order: explicit *join_keys* (when all present in
    both frames) → :func:`_infer_join_keys` → positional fallback. The keyed
    path outer-joins on the keys, reporting rows present in only one frame and
    non-key cell differences (numeric within *float_tolerance*, others by
    equality). The positional path stable-sorts both frames by all columns and
    compares row-aligned. Detail output is bounded to a small sample.

    Args:
        ref: The reference (SAS) frame.
        actual: The migrated (Python) frame.
        join_keys: Explicit, already-lowercased key columns (may be empty).
        float_tolerance: Relative tolerance for numeric cell comparison.

    Returns:
        A ``row_hash_diff`` check-result dict.
    """
    resolved = [k for k in join_keys if k in ref.columns and k in actual.columns]
    if join_keys and not resolved:
        # Configured keys are absent from the frames — fall through to inference.
        logger.warning("row_hash_diff: configured join_keys %s not found; inferring", join_keys)
    if not resolved:
        resolved = _infer_join_keys(ref, actual)

    if not resolved:
        return _compare_positional(ref, actual, float_tolerance)
    return _compare_keyed(ref, actual, resolved, float_tolerance)


class ReconciliationService:
    """Run post-migration checks comparing generated output to a reference CSV."""

    def run(
        self,
        ref_csv_path: str,
        python_code: str,
        backend: ComputeBackend,
        ref_sas7bdat_path: str = "",
        recon_config: ReconConfig | None = None,
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
            recon_config: Optional record-level reconciliation config (join keys
                and float tolerance). Defaults to :class:`ReconConfig`.

        Returns:
            Report dict: ``{ "checks": [ { "name", "status", "detail?" }, … ] }``
        """
        config = recon_config or ReconConfig()
        checks: list[dict[str, Any]] = []

        if not ref_sas7bdat_path and not ref_csv_path:
            # No reference data supplied — skip reconciliation entirely
            return {"checks": checks}

        try:
            actual_df = self._exec_pipeline(python_code, backend)
        except Exception as exc:
            error_detail = str(exc)
            logger.warning("Reconciliation execution error: %s", error_detail, exc_info=True)
            checks.append(_check_result("execution", passed=False, detail=error_detail))
            return {"checks": checks}

        try:
            if ref_sas7bdat_path:
                ref_df = cast(pd.DataFrame, backend.read_sas7bdat(ref_sas7bdat_path))
            else:
                ref_df = cast(pd.DataFrame, backend.read_csv(ref_csv_path))
        except Exception as exc:
            error_detail = str(exc)
            logger.warning("Reconciliation reference load error: %s", error_detail, exc_info=True)
            checks.append(_check_result("execution", passed=False, detail=error_detail))
            # SAS: reconciliation.py:output_schema — pipeline ran; capture schema even if ref fails
            output_schema_on_ref_fail: dict[str, Any] = {
                "columns": list(actual_df.columns),
                "dtypes": {col: str(dtype) for col, dtype in actual_df.dtypes.items()},
            }
            return {"checks": checks, "output_schema": output_schema_on_ref_fail}

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

        checks.append(_schema_parity(ref_df, actual_df))
        checks.append(_row_count(ref_df, actual_df))
        checks.append(_aggregate_parity(ref_df, actual_df))
        checks.append(
            _row_hash_diff(
                ref_df,
                actual_df,
                join_keys=config.join_keys,
                float_tolerance=config.float_tolerance,
            )
        )
        for c in checks:
            status = c.get("status", "?")
            name = c.get("name", "?")
            detail = c.get("detail", "")
            if status == "pass":
                logger.info("recon check %-20s PASS", name)
            else:
                logger.warning("recon check %-20s FAIL  %s", name, detail)
        all_passed = all(c.get("status") == "pass" for c in checks)
        logger.info(
            "reconciliation summary: %s (%d checks)", "PASS" if all_passed else "FAIL", len(checks)
        )
        # SAS: reconciliation.py:output_schema — capture actual output schema after execution
        output_schema: dict[str, Any] = {
            "columns": list(actual_df.columns),
            "dtypes": {col: str(dtype) for col, dtype in actual_df.dtypes.items()},
        }
        return {"checks": checks, "output_schema": output_schema}

    @staticmethod
    def _exec_pipeline(python_code: str, backend: ComputeBackend) -> pd.DataFrame:
        """Execute *python_code* and extract the pipeline output DataFrame.

        The generated code runs with ``backend``, ``pd``, and a real local
        SparkSession injected.  Spark DataFrames are converted to pandas before
        the checks run.

        Args:
            python_code: Python source string from CodeGenerator.
            backend: ComputeBackend instance available to the generated code.

        Returns:
            The output DataFrame produced by the pipeline.

        Raises:
            ValueError: If no DataFrame is found in the execution namespace.
        """
        spark = _get_spark()
        namespace: dict[str, Any] = {"backend": backend, "pd": pd}
        if spark is not None:
            namespace["spark"] = spark
        _safe_exec(python_code, namespace)

        # Prefer an explicit "result" variable; fall back to last DataFrame-like value.
        candidate = namespace.get("result")
        if candidate is not None:
            as_pd = _to_pandas(candidate)
            if as_pd is not None:
                return as_pd

        for v in reversed(list(namespace.values())):
            as_pd = _to_pandas(v)
            if as_pd is not None:
                return as_pd

        raise ValueError(
            "Generated pipeline produced no DataFrame in its namespace. "
            "Ensure the final output is assigned to a variable named 'result'."
        )


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
        data_dir: str = "",
        session_dir: str = "",
        recon_config: ReconConfig | None = None,
    ) -> dict[str, Any]:
        """Call the executor synchronously (intended for asyncio.to_thread use).

        Args:
            python_code: Python source to execute remotely.
            ref_csv_path: Path to reference CSV (may be empty string).
            ref_sas7bdat_path: Path to reference .sas7bdat (may be empty string).
            data_dir: Directory where uploaded data files are stored; executor
                rewrites /workspace/data/ references to this path before running.
            session_dir: If non-empty, path to the per-job DataFrame parquet cache;
                forwarded to the executor so it can pre-load prior blocks' outputs.
            recon_config: Optional record-level reconciliation config; serialized
                to a plain dict for the wire (``{}`` when ``None``).

        Returns:
            Parsed JSON response body from the executor.
        """
        url = f"{worker_settings.executor_url}/execute"
        payload = {
            "code": python_code,
            "ref_csv_path": ref_csv_path,
            "ref_sas7bdat_path": ref_sas7bdat_path,
            "data_dir": data_dir,
            "session_dir": session_dir,
            "recon_config": recon_config.model_dump() if recon_config else {},
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
        data_dir: str = "",
        session_dir: str = "",
        recon_config: ReconConfig | None = None,
    ) -> dict[str, Any]:
        """Post the generated code to the executor and return reconciliation results.

        Signature matches :meth:`ReconciliationService.run` so callers can swap
        implementations without changing call sites.

        Args:
            ref_csv_path: Path to reference CSV (may be empty string).
            python_code: Generated Python pipeline source.
            backend: Unused — kept for interface parity with ReconciliationService.
            ref_sas7bdat_path: Optional path to reference .sas7bdat.
            data_dir: Directory where uploaded data files are stored; forwarded to
                the executor so it can rewrite /workspace/data/ paths.
            session_dir: If non-empty, path to the per-job DataFrame parquet cache;
                forwarded to the executor so prior blocks' outputs are pre-loaded.
            recon_config: Optional record-level reconciliation config forwarded to
                the executor over the HTTP boundary.

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
                data_dir,
                session_dir,
                recon_config,
            )
            checks = raw.get("checks") or []
            runtime_error: str = raw.get("error") or ""
            stderr: str = raw.get("stderr") or ""
            # SAS: reconciliation.py:result_dtypes — forward executor dtype info as output_schema
            result_columns: list[str] = raw.get("result_columns") or []
            result_dtypes: dict[str, str] = raw.get("result_dtypes") or {}
            result_json = raw.get("result_json")
            for c in checks:
                name = c.get("name", "?")
                detail = c.get("detail", "")
                if c.get("status") == "pass":
                    logger.info("recon check %-20s PASS", name)
                else:
                    logger.warning("recon check %-20s FAIL  %s", name, detail)
            if runtime_error:
                logger.warning("executor runtime error: %s", runtime_error[:500])
            if checks:
                all_passed = all(c.get("status") == "pass" for c in checks)
                logger.info(
                    "reconciliation summary: %s (%d checks)",
                    "PASS" if all_passed else "FAIL",
                    len(checks),
                )
            output_schema: dict[str, Any] | None = None
            if result_columns:
                output_schema = {
                    "columns": result_columns,
                    "dtypes": result_dtypes,
                }
            result: dict[str, Any] = {"checks": checks}
            if runtime_error:
                result["runtime_error"] = runtime_error
            if stderr:
                result["stderr"] = stderr
            if output_schema is not None:
                result["output_schema"] = output_schema
            # Carry the executor's actual output rows so the worker can run an
            # in-process re-comparison (F15 LLM join-key resolution) without
            # re-executing the pipeline. Optional — absent for older executors.
            if result_json is not None:
                result["result_json"] = result_json
            if result_columns is not None:
                result["result_columns"] = result_columns
            return result
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            logger.warning("RemoteReconciliationService: executor unreachable: %s", exc)
            return {"checks": []}
        except Exception as exc:
            logger.warning("RemoteReconciliationService: unexpected error: %s", exc)
            return {"checks": []}
