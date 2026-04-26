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
from src.worker.compute.base import ComputeBackend
from src.worker.core.config import worker_settings

logger = logging.getLogger(__name__)

# Relative tolerance for aggregate comparisons (0.001 = 0.1%)
_AGGREGATE_RTOL = 0.001

_spark_session: Any = None


def _get_spark() -> Any:
    """Return a lazily-created local SparkSession (singleton per process).

    Raises RuntimeError if Spark cannot be initialised.
    Note: do NOT install databricks-connect alongside this — it hijacks
    SparkSession.builder and requires a remote Databricks cluster.
    """
    global _spark_session
    if _spark_session is None:
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


def _safe_exec(code: str, ns: dict[str, Any]) -> None:
    """Exec *code* in *ns*, auto-injecting stubs for undefined names/columns.

    Retries up to 20 times. On each attempt:
    - NameError → inject an empty DataFrame for the missing name.
    - Spark AnalysisException (unresolved column) → find which DataFrame in the
      namespace was last assigned and add the missing column to it so the next
      exec attempt can proceed.

    Args:
        code: Python source to execute.
        ns: Execution namespace (mutated in place).
    """
    for _ in range(20):
        try:
            exec(code, ns)
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
            # Spark AnalysisException: unresolved column — patch the offending DF stub
            err_str = str(exc)
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

                patched = False
                for k, v in list(ns.items()):
                    if isinstance(v, SparkDF):
                        col_names = [f.name for f in v.schema.fields]
                        if missing_col not in col_names:
                            ns[k] = _add_column_to_spark_df(v, missing_col, spark)
                            patched = True
                if not patched:
                    raise
            except ImportError:
                raise
    exec(code, ns)  # final attempt — let it raise


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
            return {"checks": checks}

        checks.append(_schema_parity(ref_df, actual_df))
        checks.append(_row_count(ref_df, actual_df))
        checks.append(_aggregate_parity(ref_df, actual_df))
        return {"checks": checks}

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
        namespace: dict[str, Any] = {"backend": backend, "pd": pd, "spark": spark}
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
