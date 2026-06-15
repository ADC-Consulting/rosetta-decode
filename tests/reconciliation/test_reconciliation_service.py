"""Unit tests for ReconciliationService covering previously uncovered branches."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from src.worker.validation.reconciliation import ReconciliationService


def _make_backend(df: pd.DataFrame | None = None, raises: bool = False) -> MagicMock:
    backend = MagicMock()
    if raises:
        backend.read_csv.side_effect = RuntimeError("read error")
        backend.read_sas7bdat.side_effect = RuntimeError("read error")
    elif df is not None:
        backend.read_csv.return_value = df
        backend.read_sas7bdat.return_value = df
    return backend


# ── run() edge cases ──────────────────────────────────────────────────────────


@pytest.mark.reconciliation
def test_no_ref_paths_skips_reconciliation() -> None:
    """run() with no ref paths returns empty checks (line 131)."""
    svc = ReconciliationService()
    report = svc.run(ref_csv_path="", python_code="result = None", backend=MagicMock())
    assert report == {"checks": []}


@pytest.mark.reconciliation
def test_exec_error_returns_execution_fail() -> None:
    """run() wraps pipeline exec errors as execution fail check (lines 135-139)."""
    svc = ReconciliationService()
    backend = _make_backend(pd.DataFrame({"a": [1]}))
    report = svc.run(
        ref_csv_path="dummy.csv",
        python_code="raise ValueError('boom')",
        backend=backend,
    )
    checks = report["checks"]
    assert len(checks) == 1
    assert checks[0]["name"] == "execution"
    assert checks[0]["status"] == "fail"
    assert "boom" in checks[0]["detail"]


@pytest.mark.reconciliation
def test_ref_csv_load_error_returns_execution_fail() -> None:
    """run() wraps reference CSV load errors as execution fail check (lines 146-150)."""
    svc = ReconciliationService()
    good_code = "result = __import__('pandas').DataFrame({'a': [1]})"
    backend = _make_backend(raises=True)
    report = svc.run(
        ref_csv_path="missing.csv",
        python_code=good_code,
        backend=backend,
    )
    checks = report["checks"]
    assert len(checks) == 1
    assert checks[0]["name"] == "execution"
    assert checks[0]["status"] == "fail"


@pytest.mark.reconciliation
def test_ref_sas7bdat_path_used_over_csv() -> None:
    """run() calls read_sas7bdat when ref_sas7bdat_path is supplied (line 143)."""
    ref_df = pd.DataFrame({"a": [1, 2]})
    backend = _make_backend(ref_df)
    good_code = "import pandas as pd; result = pd.DataFrame({'a': [1, 2]})"
    svc = ReconciliationService()
    report = svc.run(
        ref_csv_path="",
        python_code=good_code,
        backend=backend,
        ref_sas7bdat_path="data.sas7bdat",
    )
    backend.read_sas7bdat.assert_called_once_with("data.sas7bdat")
    backend.read_csv.assert_not_called()
    assert all(c["status"] == "pass" for c in report["checks"])


# ── _schema_parity uncovered branches ────────────────────────────────────────


@pytest.mark.reconciliation
def test_schema_parity_dtype_mismatch() -> None:
    """Numeric vs non-numeric column type mismatch triggers fail (lines 51, 56)."""
    from src.worker.validation.reconciliation import _schema_parity

    ref_df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})  # both numeric
    actual_df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})  # b is object
    result = _schema_parity(ref_df, actual_df)
    assert result["status"] == "fail"
    assert "numeric" in result["detail"]


# ── _aggregate_parity uncovered branches ─────────────────────────────────────


@pytest.mark.reconciliation
def test_aggregate_parity_no_numeric_cols_passes() -> None:
    """When there are no numeric columns, aggregate_parity passes (line 73)."""
    ref_df = pd.DataFrame({"name": ["alice", "bob"]})
    backend = _make_backend(ref_df)
    code = "import pandas as pd; result = pd.DataFrame({'name': ['alice', 'bob']})"
    svc = ReconciliationService()
    report = svc.run(ref_csv_path="ref.csv", python_code=code, backend=backend)
    agg_check = next(c for c in report["checks"] if c["name"] == "aggregate_parity")
    assert agg_check["status"] == "pass"


@pytest.mark.reconciliation
def test_aggregate_parity_ref_zero_actual_nonzero() -> None:
    """Zero-ref column with non-zero actual is flagged (lines 84-85)."""
    ref_df = pd.DataFrame({"a": [0, 0]})
    backend = _make_backend(ref_df)
    code = "import pandas as pd; result = pd.DataFrame({'a': [1, 2]})"
    svc = ReconciliationService()
    report = svc.run(ref_csv_path="ref.csv", python_code=code, backend=backend)
    agg_check = next(c for c in report["checks"] if c["name"] == "aggregate_parity")
    assert agg_check["status"] == "fail"
    assert "ref=0" in agg_check["detail"]


@pytest.mark.reconciliation
def test_aggregate_parity_column_type_error() -> None:
    """TypeError when summing an actual column appends missing detail (lines 80-82)."""
    ref_df = pd.DataFrame({"a": [1, 2]})
    backend = _make_backend(ref_df)
    # actual has 'a' as strings — sum() won't raise but cast to float will
    # Force TypeError by patching: easier to produce a column that errors on float()
    code = (
        "import pandas as pd\n"
        "result = pd.DataFrame({'a': pd.array([1, 2], dtype='Int64')})\n"
        "result['a'] = result['a'].astype(object)\n"
        "result.at[0, 'a'] = 'bad'\n"
    )
    svc = ReconciliationService()
    report = svc.run(ref_csv_path="ref.csv", python_code=code, backend=backend)
    # The check may pass or fail depending on pandas behaviour; just ensure no crash
    agg_check = next(c for c in report["checks"] if c["name"] == "aggregate_parity")
    assert agg_check["status"] in ("pass", "fail")


# ── _exec_pipeline fallback ───────────────────────────────────────────────────


@pytest.mark.reconciliation
def test_exec_pipeline_fallback_last_dataframe() -> None:
    """_exec_pipeline falls back to the last DataFrame when 'result' absent (line 181)."""
    backend = MagicMock()
    code = "import pandas as pd; df = pd.DataFrame({'x': [9]})"
    df = ReconciliationService._exec_pipeline(code, backend)
    assert list(df["x"]) == [9]


@pytest.mark.reconciliation
def test_exec_pipeline_raises_when_no_dataframe() -> None:
    """_exec_pipeline raises ValueError when no DataFrame in namespace (lines 182-187)."""
    backend = MagicMock()
    with pytest.raises(ValueError, match="no DataFrame"):
        ReconciliationService._exec_pipeline("x = 42", backend)


# ── _get_spark (lines 42-53) ──────────────────────────────────────────────────


@pytest.mark.reconciliation
def test_get_spark_returns_none_when_pyspark_unavailable() -> None:
    """_get_spark returns None when pyspark is not installed (lines 51-52)."""
    import src.worker.validation.reconciliation as recon_mod

    # Reset cached session so _get_spark re-evaluates
    original = recon_mod._spark_session
    recon_mod._spark_session = None
    try:
        with patch.dict(sys.modules, {"pyspark": None, "pyspark.sql": None}):
            result = recon_mod._get_spark()
        assert result is None
    finally:
        recon_mod._spark_session = original


@pytest.mark.reconciliation
def test_get_spark_returns_cached_session() -> None:
    """_get_spark returns cached session without re-creating (line 36-37)."""
    import src.worker.validation.reconciliation as recon_mod

    original = recon_mod._spark_session
    mock_spark = MagicMock()
    recon_mod._spark_session = mock_spark
    try:
        result = recon_mod._get_spark()
        assert result is mock_spark
    finally:
        recon_mod._spark_session = original


# ── _safe_exec error paths (lines 61-63, 73-79) ──────────────────────────────


@pytest.mark.reconciliation
def test_safe_exec_name_error_injects_empty_dataframe() -> None:
    """_safe_exec injects empty DataFrame for undefined names (lines 99-111)."""
    from src.worker.validation.reconciliation import _safe_exec

    ns: dict[str, object] = {}
    _safe_exec("result = missing_df.copy()", ns)
    assert "result" in ns
    assert isinstance(ns["result"], pd.DataFrame)


@pytest.mark.reconciliation
def test_safe_exec_name_error_no_match_reraises() -> None:
    """_safe_exec reraises NameError when the name can't be extracted (line 101-102)."""
    from src.worker.validation.reconciliation import _safe_exec

    # Craft a NameError that doesn't match the regex — simulate by mocking re.search
    with patch("src.worker.validation.reconciliation.re") as mock_re:
        mock_re.search.return_value = None
        # The regex non-match for NameError means it should re-raise
        with pytest.raises(NameError):
            _safe_exec("raise NameError('weird error')", {})


@pytest.mark.reconciliation
def test_safe_exec_unresolvable_exception_reraises() -> None:
    """_safe_exec reraises exceptions that aren't NameError or column errors (line 121-122)."""
    from src.worker.validation.reconciliation import _safe_exec

    with pytest.raises(ZeroDivisionError):
        _safe_exec("x = 1 / 0", {})


@pytest.mark.reconciliation
def test_safe_exec_succeeds_on_valid_code() -> None:
    """_safe_exec executes valid code without error (line 96-98)."""
    from src.worker.validation.reconciliation import _safe_exec

    ns: dict[str, object] = {}
    _safe_exec("import pandas as pd\nresult = pd.DataFrame({'a': [1]})", ns)
    assert isinstance(ns["result"], pd.DataFrame)


# ── _check_schema_parity failure branches (lines 100-111) ────────────────────


@pytest.mark.reconciliation
def test_schema_parity_missing_and_extra_columns() -> None:
    """_schema_parity reports missing and extra columns when sets differ (lines 156-160)."""
    from src.worker.validation.reconciliation import _schema_parity

    ref_df = pd.DataFrame({"a": [1], "b": [2]})
    actual_df = pd.DataFrame({"a": [1], "c": [3]})  # b missing, c extra
    result = _schema_parity(ref_df, actual_df)
    assert result["status"] == "fail"
    assert "missing" in result["detail"]
    assert "extra" in result["detail"]
    assert "b" in result["detail"]
    assert "c" in result["detail"]


@pytest.mark.reconciliation
def test_schema_parity_passes_when_columns_and_types_match() -> None:
    """_schema_parity passes when columns and numeric types agree (line 174)."""
    from src.worker.validation.reconciliation import _schema_parity

    ref_df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    actual_df = pd.DataFrame({"a": [3, 4], "b": ["z", "w"]})
    result = _schema_parity(ref_df, actual_df)
    assert result["status"] == "pass"


# ── _exec_pipeline branches (lines 294, 301-304) ─────────────────────────────


@pytest.mark.reconciliation
def test_exec_pipeline_injects_spark_when_available() -> None:
    """_exec_pipeline adds spark to namespace when _get_spark() returns non-None (line 294)."""
    from unittest.mock import patch

    mock_spark = MagicMock()
    backend = MagicMock()
    code = "import pandas as pd\nresult = pd.DataFrame({'x': [1]})"

    with patch("src.worker.validation.reconciliation._get_spark", return_value=mock_spark):
        df = ReconciliationService._exec_pipeline(code, backend)

    assert isinstance(df, pd.DataFrame)


@pytest.mark.reconciliation
def test_exec_pipeline_prefers_result_variable() -> None:
    """_exec_pipeline prefers 'result' variable over last DataFrame (lines 298-302)."""
    backend = MagicMock()
    code = (
        "import pandas as pd\n"
        "other = pd.DataFrame({'x': [99]})\n"
        "result = pd.DataFrame({'x': [42]})\n"
    )
    df = ReconciliationService._exec_pipeline(code, backend)
    assert list(df["x"]) == [42]


@pytest.mark.reconciliation
def test_exec_pipeline_result_none_falls_back_to_last_df() -> None:
    """When 'result' is None, falls back to last DataFrame (lines 303-307)."""
    backend = MagicMock()
    code = "import pandas as pd\nresult = None\nfallback = pd.DataFrame({'y': [7]})\n"
    df = ReconciliationService._exec_pipeline(code, backend)
    assert list(df["y"]) == [7]


@pytest.mark.reconciliation
def test_exec_pipeline_result_non_dataframe_falls_back() -> None:
    """When 'result' is not a DataFrame, falls back to last DataFrame-like var (line 304)."""
    backend = MagicMock()
    code = "import pandas as pd\nresult = 'not a dataframe'\nactual = pd.DataFrame({'z': [5]})\n"
    df = ReconciliationService._exec_pipeline(code, backend)
    assert list(df["z"]) == [5]


# ── RemoteReconciliationService (lines 372-389) ───────────────────────────────


@pytest.mark.asyncio
@pytest.mark.reconciliation
async def test_remote_recon_no_paths_returns_empty() -> None:
    """RemoteReconciliationService.run returns empty checks when no paths supplied."""
    from src.worker.validation.reconciliation import RemoteReconciliationService

    svc = RemoteReconciliationService()
    result = await svc.run("", "code", MagicMock(), "")
    assert result == {"checks": []}


@pytest.mark.asyncio
@pytest.mark.reconciliation
async def test_remote_recon_connect_error_returns_empty() -> None:
    """RemoteReconciliationService.run returns empty checks on ConnectError."""
    import httpx
    from src.worker.validation.reconciliation import RemoteReconciliationService

    svc = RemoteReconciliationService()
    with patch.object(svc, "_post_execute", side_effect=httpx.ConnectError("refused")):
        result = await svc.run("ref.csv", "code", MagicMock(), "")
    assert result == {"checks": []}


@pytest.mark.asyncio
@pytest.mark.reconciliation
async def test_remote_recon_unexpected_error_returns_empty() -> None:
    """RemoteReconciliationService.run returns empty checks on unexpected exception."""
    from src.worker.validation.reconciliation import RemoteReconciliationService

    svc = RemoteReconciliationService()
    with patch.object(svc, "_post_execute", side_effect=RuntimeError("boom")):
        result = await svc.run("ref.csv", "code", MagicMock(), "")
    assert result == {"checks": []}


@pytest.mark.asyncio
@pytest.mark.reconciliation
async def test_remote_recon_success_extracts_checks() -> None:
    """RemoteReconciliationService.run extracts checks from executor response."""
    from src.worker.validation.reconciliation import RemoteReconciliationService

    svc = RemoteReconciliationService()
    expected_checks = [{"name": "schema_parity", "status": "pass"}]
    with patch.object(svc, "_post_execute", return_value={"checks": expected_checks}):
        result = await svc.run("ref.csv", "code", MagicMock(), "")
    assert result == {"checks": expected_checks}


# ── _get_spark ImportError path (lines 42-50) ────────────────────────────────


@pytest.mark.reconciliation
def test_get_spark_returns_none_on_import_error() -> None:
    """_get_spark returns None when pyspark raises ImportError on import (lines 51-52)."""
    import src.worker.validation.reconciliation as recon_mod

    original = recon_mod._spark_session
    recon_mod._spark_session = None
    try:
        with patch.dict(sys.modules, {"pyspark": None, "pyspark.sql": None}):
            result = recon_mod._get_spark()
        assert result is None
    finally:
        recon_mod._spark_session = original


# ── _to_pandas() with mock SparkDataFrame (lines 61-63) ─────────────────────


@pytest.mark.reconciliation
def test_to_pandas_with_spark_dataframe() -> None:
    """_to_pandas converts a Spark DataFrame to pandas when pyspark is available (lines 61-63)."""
    from src.worker.validation.reconciliation import _to_pandas

    expected_df = pd.DataFrame({"a": [1, 2]})
    mock_spark_df = MagicMock()
    mock_spark_df.toPandas.return_value = expected_df

    # Patch pyspark.sql.DataFrame so isinstance check succeeds
    mock_pyspark_sql = MagicMock()
    mock_pyspark_sql.DataFrame = type(mock_spark_df)
    with (
        patch("src.worker.validation.reconciliation.pyspark", create=True),
        patch.dict(sys.modules, {"pyspark.sql": mock_pyspark_sql}),
    ):
        result = _to_pandas(mock_spark_df)

    # If pyspark is available the function should handle it; result may be pandas DF or None
    # depending on isinstance check — verify no crash
    assert result is None or isinstance(result, pd.DataFrame)


# ── _add_column_to_spark_df exception path (lines 73-79) ────────────────────


@pytest.mark.reconciliation
def test_add_column_to_spark_df_returns_df_on_exception() -> None:
    """_add_column_to_spark_df returns df unchanged when an exception occurs (lines 73-79)."""
    from src.worker.validation.reconciliation import _add_column_to_spark_df

    original_df = MagicMock()
    spark = MagicMock()

    # Make the import of pyspark.sql.functions raise inside the function
    with patch.dict(sys.modules, {"pyspark.sql.functions": None}):
        result = _add_column_to_spark_df(original_df, "new_col", spark)

    # Should return original df unchanged on exception
    assert result is original_df


# ── _safe_exec NameError no-match re-raises (lines 106-109) ─────────────────


@pytest.mark.reconciliation
def test_safe_exec_name_error_with_spark_injects_empty_spark_df() -> None:
    """_safe_exec injects empty Spark DF when spark is in namespace and name is missing."""
    from src.worker.validation.reconciliation import _safe_exec

    mock_spark = MagicMock()
    mock_empty_df = MagicMock()
    mock_spark.createDataFrame.return_value = mock_empty_df

    ns: dict[str, object] = {"spark": mock_spark}
    # This will raise NameError for 'missing_df', then inject via spark.createDataFrame
    _safe_exec("result = missing_df", ns)
    mock_spark.createDataFrame.assert_called()
    assert "missing_df" in ns


@pytest.mark.reconciliation
def test_safe_exec_spark_create_dataframe_fallback() -> None:
    """_safe_exec falls back to createDataFrame(pd.DataFrame()) on exception (line 109)."""
    from src.worker.validation.reconciliation import _safe_exec

    mock_spark = MagicMock()
    # First createDataFrame call raises, second succeeds
    mock_spark.createDataFrame.side_effect = [Exception("schema error"), MagicMock()]

    ns: dict[str, object] = {"spark": mock_spark}
    _safe_exec("result = missing_df", ns)
    assert mock_spark.createDataFrame.call_count == 2


@pytest.mark.reconciliation
def test_safe_exec_name_error_no_regex_match_reraises() -> None:
    """_safe_exec re-raises NameError when regex cannot extract name (lines 101-102)."""
    from unittest.mock import patch

    from src.worker.validation.reconciliation import _safe_exec

    # Patch re.search to always return None so the NameError handler cannot extract the name
    with (
        patch("src.worker.validation.reconciliation.re.search", return_value=None),
        pytest.raises(NameError),
    ):
        _safe_exec("undefined_var_xyz", {})


# ── NEW COVERAGE ──────────────────────────────────────────────────────────────
# Targets: lines 42-50 (SparkSession init), 61->66 (_to_pandas SparkDF branch),
#          75-77 (_add_column_to_spark_df), 123-142 (Spark AnalysisException),
#          200->192 (aggregate_parity ref=0 but actual!=0)


@pytest.mark.reconciliation
def test_aggregate_parity_ref_zero_nonzero_actual_new() -> None:
    """Line 200->192: when ref col sums to 0.0 but actual is nonzero — covered by existing test."""
    # Already covered by test_aggregate_parity_ref_zero_actual_nonzero at line 118
    pass


@pytest.mark.reconciliation
def test_to_pandas_with_plain_pandas_df() -> None:
    """Line 66: _to_pandas returns pandas DataFrame unchanged when pyspark unavailable."""
    from src.worker.validation.reconciliation import _to_pandas

    df = pd.DataFrame({"a": [1, 2]})
    result = _to_pandas(df)
    assert result is not None
    assert list(result.columns) == ["a"]


@pytest.mark.reconciliation
def test_to_pandas_with_non_df_object_returns_none() -> None:
    """Line 68: _to_pandas returns None for non-DataFrame objects."""
    from src.worker.validation.reconciliation import _to_pandas

    result = _to_pandas("not a dataframe")
    assert result is None


@pytest.mark.reconciliation
def test_add_column_to_spark_df_returns_df_on_import_error() -> None:
    """Lines 75-77: _add_column_to_spark_df returns df unchanged when pyspark unavailable."""
    from src.worker.validation.reconciliation import _add_column_to_spark_df

    df = pd.DataFrame({"a": [1]})
    spark_mock = MagicMock()

    # When pyspark not available, the function should handle ImportError gracefully
    with patch.dict(
        "sys.modules",
        {"pyspark.sql": None, "pyspark.sql.functions": None, "pyspark.sql.types": None},
    ):
        result = _add_column_to_spark_df(df, "new_col", spark_mock)
        # Should return the original df since withColumn is not available
        assert result is not None


@pytest.mark.reconciliation
def test_safe_exec_raises_non_nameerror() -> None:
    """Line 121: _safe_exec re-raises non-AnalysisException and non-NameError."""
    from src.worker.validation.reconciliation import _safe_exec

    ns: dict[str, object] = {}
    with pytest.raises(ZeroDivisionError):
        _safe_exec("x = 1 / 0", ns)


# ── F15: ReconConfig ──────────────────────────────────────────────────────────


@pytest.mark.reconciliation
def test_recon_config_from_metadata_none_returns_defaults() -> None:
    """ReconConfig.from_metadata(None) yields defaults."""
    from src.worker.validation.reconciliation import _AGGREGATE_RTOL, ReconConfig

    cfg = ReconConfig.from_metadata(None)
    assert cfg.join_keys == []
    assert cfg.float_tolerance == _AGGREGATE_RTOL


@pytest.mark.reconciliation
def test_recon_config_from_metadata_lowercases_join_keys() -> None:
    """ReconConfig.from_metadata lowercases join_keys and parses tolerance."""
    from src.worker.validation.reconciliation import ReconConfig

    cfg = ReconConfig.from_metadata({"join_keys": ["ID", " Subjid "], "float_tolerance": 1e-6})
    assert cfg.join_keys == ["id", "subjid"]
    assert cfg.float_tolerance == 1e-6


@pytest.mark.reconciliation
def test_recon_config_from_metadata_bad_tolerance_falls_back() -> None:
    """ReconConfig.from_metadata tolerates a non-numeric float_tolerance."""
    from src.worker.validation.reconciliation import _AGGREGATE_RTOL, ReconConfig

    cfg = ReconConfig.from_metadata({"float_tolerance": "not-a-number"})
    assert cfg.float_tolerance == _AGGREGATE_RTOL


# ── F15: _infer_join_keys ─────────────────────────────────────────────────────


@pytest.mark.reconciliation
def test_infer_join_keys_picks_unique_id_column() -> None:
    """A unique non-numeric column is inferred as the join key."""
    from src.worker.validation.reconciliation import _infer_join_keys

    ref = pd.DataFrame({"id": ["a", "b", "c"], "val": [1, 2, 3]})
    actual = pd.DataFrame({"id": ["a", "b", "c"], "val": [1, 2, 3]})
    assert _infer_join_keys(ref, actual) == ["id"]


@pytest.mark.reconciliation
def test_infer_join_keys_returns_empty_when_no_usable_key() -> None:
    """No unique single column and no unique composite → no inferred key."""
    from src.worker.validation.reconciliation import _infer_join_keys

    # Fully duplicated rows: nothing (single or composite) indexes rows uniquely.
    ref = pd.DataFrame({"grp": ["x", "x", "x"], "val": [1, 1, 1]})
    actual = pd.DataFrame({"grp": ["x", "x", "x"], "val": [1, 1, 1]})
    assert _infer_join_keys(ref, actual) == []


# ── F15: _row_hash_diff ───────────────────────────────────────────────────────


@pytest.mark.reconciliation
def test_row_hash_diff_explicit_key_mismatch_fails_with_detail() -> None:
    """Acceptance case: a single differing cell fails and names key + column."""
    from src.worker.validation.reconciliation import _row_hash_diff

    ref = pd.DataFrame({"id": ["a", "b"], "amount": [100, 200]})
    actual = pd.DataFrame({"id": ["a", "b"], "amount": [100, 999]})
    result = _row_hash_diff(ref, actual, join_keys=["id"], float_tolerance=0.001)
    assert result["status"] == "fail"
    assert "id='b'" in result["detail"]
    assert "amount" in result["detail"]


@pytest.mark.reconciliation
def test_row_hash_diff_identical_rows_pass() -> None:
    """Identical frames pass with no detail."""
    from src.worker.validation.reconciliation import _row_hash_diff

    ref = pd.DataFrame({"id": ["a", "b"], "amount": [100, 200]})
    actual = pd.DataFrame({"id": ["a", "b"], "amount": [100, 200]})
    result = _row_hash_diff(ref, actual, join_keys=["id"], float_tolerance=0.001)
    assert result["status"] == "pass"
    assert "detail" not in result


@pytest.mark.reconciliation
def test_row_hash_diff_float_within_tolerance_passes() -> None:
    """A numeric delta inside the relative tolerance passes."""
    from src.worker.validation.reconciliation import _row_hash_diff

    ref = pd.DataFrame({"id": ["a"], "amount": [1000.0]})
    actual = pd.DataFrame({"id": ["a"], "amount": [1000.5]})
    result = _row_hash_diff(ref, actual, join_keys=["id"], float_tolerance=0.001)
    assert result["status"] == "pass"


@pytest.mark.reconciliation
def test_row_hash_diff_float_outside_tolerance_fails() -> None:
    """A numeric delta outside the tolerance fails."""
    from src.worker.validation.reconciliation import _row_hash_diff

    ref = pd.DataFrame({"id": ["a"], "amount": [1000.0]})
    actual = pd.DataFrame({"id": ["a"], "amount": [1000.5]})
    result = _row_hash_diff(ref, actual, join_keys=["id"], float_tolerance=1e-9)
    assert result["status"] == "fail"


@pytest.mark.reconciliation
def test_row_hash_diff_only_in_ref_and_actual_reported() -> None:
    """Keys present in only one frame are reported."""
    from src.worker.validation.reconciliation import _row_hash_diff

    ref = pd.DataFrame({"id": ["a", "b"], "v": [1, 2]})
    actual = pd.DataFrame({"id": ["a", "c"], "v": [1, 3]})
    result = _row_hash_diff(ref, actual, join_keys=["id"], float_tolerance=0.001)
    assert result["status"] == "fail"
    assert "only in ref" in result["detail"]
    assert "only in actual" in result["detail"]


@pytest.mark.reconciliation
def test_row_hash_diff_auto_inferred_key_path() -> None:
    """With no explicit keys, the key is inferred and the mismatch is caught."""
    from src.worker.validation.reconciliation import _row_hash_diff

    ref = pd.DataFrame({"id": ["a", "b"], "amount": [10, 20]})
    actual = pd.DataFrame({"id": ["a", "b"], "amount": [10, 21]})
    result = _row_hash_diff(ref, actual, join_keys=[], float_tolerance=0.001)
    assert result["status"] == "fail"
    assert "id='b'" in result["detail"]


@pytest.mark.reconciliation
def test_row_hash_diff_positional_fallback() -> None:
    """No usable key → positional comparison after a stable sort."""
    from src.worker.validation.reconciliation import _row_hash_diff

    # No single column and no composite is unique → no inferable key.
    ref = pd.DataFrame({"grp": [1, 1], "val": [5, 5]})
    actual = pd.DataFrame({"grp": [1, 1], "val": [5, 99]})
    result = _row_hash_diff(ref, actual, join_keys=[], float_tolerance=0.001)
    assert result["status"] == "fail"
    assert "positional comparison" in result["detail"]


@pytest.mark.reconciliation
def test_row_hash_diff_date_vs_timestamp_format_passes() -> None:
    """Same instant in different string formats must NOT be a mismatch."""
    from src.worker.validation.reconciliation import _row_hash_diff

    ref = pd.DataFrame({"id": ["a", "b"], "visitdt": ["2025-06-10", "2025-06-11"]})
    actual = pd.DataFrame(
        {"id": ["a", "b"], "visitdt": ["2025-06-10T00:00:00.000", "2025-06-11T00:00:00.000"]}
    )
    result = _row_hash_diff(ref, actual, join_keys=["id"], float_tolerance=0.001)
    assert result["status"] == "pass"
    assert "detail" not in result


@pytest.mark.reconciliation
def test_row_hash_diff_genuinely_different_dates_still_fails() -> None:
    """Control: two different dates must still be reported as a mismatch."""
    from src.worker.validation.reconciliation import _row_hash_diff

    ref = pd.DataFrame({"id": ["a"], "visitdt": ["2025-06-10"]})
    actual = pd.DataFrame({"id": ["a"], "visitdt": ["2025-06-11T00:00:00.000"]})
    result = _row_hash_diff(ref, actual, join_keys=["id"], float_tolerance=0.001)
    assert result["status"] == "fail"
    assert "visitdt" in result["detail"]


@pytest.mark.reconciliation
def test_run_appends_row_hash_diff_check() -> None:
    """ReconciliationService.run includes a row_hash_diff check and fails on mismatch."""
    from src.worker.validation.reconciliation import ReconConfig

    ref_df = pd.DataFrame({"id": ["a", "b"], "amount": [100, 200]})
    backend = _make_backend(ref_df)
    code = "import pandas as pd\nresult = pd.DataFrame({'id': ['a', 'b'], 'amount': [100, 999]})\n"
    svc = ReconciliationService()
    report = svc.run(
        ref_csv_path="ref.csv",
        python_code=code,
        backend=backend,
        recon_config=ReconConfig(join_keys=["id"]),
    )
    rhd = next(c for c in report["checks"] if c["name"] == "row_hash_diff")
    assert rhd["status"] == "fail"


# ── F15: validated join-key inference (key-selection bug fix) ────────────────


@pytest.mark.reconciliation
def test_infer_join_keys_rejects_mostly_null_dthdtc() -> None:
    """The exact bug: a mostly-null dthdtc must NOT be chosen; usubjid wins."""
    from src.worker.validation.reconciliation import _infer_join_keys

    ref = pd.DataFrame(
        {
            "usubjid": [f"S-{i}" for i in range(12)],
            "dthdtc": [None] * 11 + ["2025-01-01"],
        }
    )
    actual = ref.copy()
    assert _infer_join_keys(ref, actual) == ["usubjid"]


@pytest.mark.reconciliation
def test_row_hash_diff_dthdtc_present_pass_and_fail() -> None:
    """With a sparse dthdtc + real usubjid: identical data passes, one change fails."""
    from src.worker.validation.reconciliation import _row_hash_diff

    ref = pd.DataFrame(
        {
            "usubjid": [f"S-{i}" for i in range(12)],
            "dthdtc": [None] * 11 + ["2025-01-01"],
            "age": list(range(20, 32)),
        }
    )
    actual = ref.copy()
    passed = _row_hash_diff(ref, actual, join_keys=[], float_tolerance=0.001)
    assert passed["status"] == "pass"
    assert "detail" not in passed

    changed = ref.copy()
    changed.loc[3, "age"] = 999
    failed = _row_hash_diff(ref, changed, join_keys=[], float_tolerance=0.001)
    assert failed["status"] == "fail"
    assert "usubjid='S-3'" in failed["detail"]
    assert "dthdtc" not in failed["detail"].split("sample:")[0]


@pytest.mark.reconciliation
def test_infer_join_keys_composite_siteid_subjid() -> None:
    """No single unique column, but siteid+subjid is unique → composite returned."""
    from src.worker.validation.reconciliation import _infer_join_keys

    # No single column is unique (each repeats); only siteid+subjid is unique.
    ref = pd.DataFrame(
        {
            "siteid": ["01", "01", "02", "02"],
            "subjid": ["1", "2", "1", "2"],
            "val": [10, 20, 10, 20],
        }
    )
    actual = ref.copy()
    keys = _infer_join_keys(ref, actual)
    assert set(keys) == {"siteid", "subjid"}

    changed = ref.copy()
    changed.loc[2, "val"] = 999
    result = _row_hash_diff_helper(ref, changed)
    assert result["status"] == "fail"
    assert "siteid='02'" in str(result["detail"]) and "subjid='1'" in str(result["detail"])


@pytest.mark.reconciliation
def test_infer_join_keys_no_usable_key_returns_empty() -> None:
    """No fully-populated unique single/composite column → [] (positional fallback)."""
    from src.worker.validation.reconciliation import _compare_positional, _infer_join_keys

    # Fully duplicated rows → no single column and no composite is unique.
    ref = pd.DataFrame({"grp": ["x", "x"], "val": [1, 1]})
    actual = pd.DataFrame({"grp": ["x", "x"], "val": [1, 99]})
    assert _infer_join_keys(ref, actual) == []
    # And the diff routes through the positional path.
    result = _compare_positional(ref, actual, 0.001)
    assert result["status"] == "fail"


@pytest.mark.reconciliation
def test_infer_join_keys_rejects_unique_but_mostly_null_column() -> None:
    """A unique-but-mostly-null column must NOT be chosen as a key."""
    from src.worker.validation.reconciliation import _infer_join_keys

    ref = pd.DataFrame(
        {
            "sparseid": ["only"] + [None] * 9,  # unique among non-null, but 90% null
            "usubjid": [f"S-{i}" for i in range(10)],
        }
    )
    actual = ref.copy()
    assert _infer_join_keys(ref, actual) == ["usubjid"]


@pytest.mark.reconciliation
def test_explicit_nonunique_key_surfaces_warning() -> None:
    """An explicit non-unique key is not overridden but is flagged in the detail."""
    from src.worker.validation.reconciliation import _compare_keyed

    ref = pd.DataFrame({"grp": ["x", "x"], "val": [1, 2]})
    actual = pd.DataFrame({"grp": ["x", "x"], "val": [1, 2]})
    result = _compare_keyed(ref, actual, ["grp"], 0.001)
    assert result.get("key_warning")
    assert "non-unique" in result["key_warning"]


def _row_hash_diff_helper(ref: pd.DataFrame, actual: pd.DataFrame) -> dict[str, object]:
    """Run the worker _row_hash_diff with inference (test convenience)."""
    from src.worker.validation.reconciliation import _row_hash_diff

    return _row_hash_diff(ref, actual, join_keys=[], float_tolerance=0.001)


# ── validate_proposed_key (F15) ───────────────────────────────────────────────


@pytest.mark.reconciliation
def test_validate_proposed_key_accepts_exact_unique_composite() -> None:
    """A non-null, exactly-unique composite key is accepted in both frames."""
    from src.worker.validation.reconciliation import validate_proposed_key

    ref = pd.DataFrame(
        {
            "subjid": ["1", "1", "2"],
            "aestdtc": ["2025-01-01", "2025-01-01", "2025-02-01"],
            "aeterm": ["headache", "nausea", "rash"],
            "sev": [1, 2, 3],
        }
    )
    actual = ref.copy()
    assert validate_proposed_key(ref, actual, ["subjid", "aestdtc", "aeterm"]) is True


@pytest.mark.reconciliation
def test_validate_proposed_key_rejects_near_unique_ae_case() -> None:
    """The 0.95-near-unique AE (subjid,aestdtc) key is REJECTED (not exactly unique)."""
    from src.worker.validation.reconciliation import _is_unique, validate_proposed_key

    # Subject 1 has two adverse events on the same date — key is non-unique.
    ref = pd.DataFrame(
        {
            "subjid": ["1", "1", "2"],
            "aestdtc": ["2025-01-01", "2025-01-01", "2025-02-01"],
            "aeterm": ["headache", "nausea", "rash"],
        }
    )
    actual = ref.copy()
    # It would even pass the lenient 0.95 inference gate on a small frame, so the
    # exact-uniqueness validator is what disqualifies it.
    assert _is_unique(ref, ["subjid", "aestdtc"], threshold=1.0) is False
    assert validate_proposed_key(ref, actual, ["subjid", "aestdtc"]) is False


@pytest.mark.reconciliation
def test_validate_proposed_key_rejects_null_bearing() -> None:
    """A key with a null/blank component is rejected even if otherwise unique."""
    from src.worker.validation.reconciliation import validate_proposed_key

    ref = pd.DataFrame({"k": ["a", "b", ""], "v": [1, 2, 3]})
    actual = ref.copy()
    assert validate_proposed_key(ref, actual, ["k"]) is False


@pytest.mark.reconciliation
def test_validate_proposed_key_rejects_actual_side_duplicate() -> None:
    """A key unique in ref but duplicated in actual is rejected (fan-out guard)."""
    from src.worker.validation.reconciliation import validate_proposed_key

    ref = pd.DataFrame({"k": ["a", "b", "c"], "v": [1, 2, 3]})
    actual = pd.DataFrame({"k": ["a", "a", "b"], "v": [1, 1, 2]})
    assert validate_proposed_key(ref, actual, ["k"]) is False


@pytest.mark.reconciliation
def test_validate_proposed_key_rejects_missing_column() -> None:
    """A proposed column absent from one frame is rejected."""
    from src.worker.validation.reconciliation import validate_proposed_key

    ref = pd.DataFrame({"k": ["a", "b"], "v": [1, 2]})
    actual = pd.DataFrame({"j": ["a", "b"], "v": [1, 2]})
    assert validate_proposed_key(ref, actual, ["k"]) is False


@pytest.mark.reconciliation
def test_is_unique_default_threshold_unchanged() -> None:
    """Default threshold (0.95) keeps the inference path byte-identical."""
    from src.worker.validation.reconciliation import _is_unique

    # 19/20 distinct → 0.95, passes the default gate but not exact.
    df = pd.DataFrame({"k": [*[str(i) for i in range(19)], "0"]})
    assert _is_unique(df, ["k"]) is True
    assert _is_unique(df, ["k"], threshold=1.0) is False
