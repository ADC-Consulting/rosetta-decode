"""Unit tests for _coerce_sas_date_columns in the reconciliation runner.

Exercises both alignment branches (object-date vs numeric, numeric vs
numeric-string IDs) and their guard paths using small hand-built pandas
DataFrames — no Spark, no file I/O.
"""

from __future__ import annotations

import pandas as pd
import pytest
from src.worker.validation.reconciliation import _coerce_sas_date_columns

pytestmark = pytest.mark.reconciliation

# SAS epoch is 1960-01-01; derive days-since-epoch so test and source agree
# on the exact integer rather than hard-coding a hand-counted value.
_SAS_EPOCH = pd.Timestamp("1960-01-01")
_DATE_STRINGS = ["2025-01-01", "2025-06-15"]
_DATE_SAS_DAYS = [(pd.Timestamp(d) - _SAS_EPOCH).days for d in _DATE_STRINGS]


def test_date_branch_normalises_both_to_sas_days() -> None:
    """ref=ISO date strings, actual=SAS-day ints → both become numeric, equal."""
    ref = pd.DataFrame({"dt": _DATE_STRINGS})
    actual = pd.DataFrame({"dt": _DATE_SAS_DAYS})

    out_ref, out_actual = _coerce_sas_date_columns(ref, actual)

    assert pd.api.types.is_numeric_dtype(out_ref["dt"])
    assert pd.api.types.is_numeric_dtype(out_actual["dt"])
    assert out_ref["dt"].tolist() == [float(d) for d in _DATE_SAS_DAYS]
    assert out_ref["dt"].tolist() == out_actual["dt"].tolist()


def test_sparse_date_column_still_normalises() -> None:
    """ref mostly blank with a few valid dates (>0.8 parseable) → normalised."""
    ref = pd.DataFrame({"dt": ["", "", *_DATE_STRINGS]})
    actual = pd.DataFrame({"dt": [0, 0, *_DATE_SAS_DAYS]})

    out_ref, out_actual = _coerce_sas_date_columns(ref, actual)

    assert pd.api.types.is_numeric_dtype(out_ref["dt"])
    assert pd.api.types.is_numeric_dtype(out_actual["dt"])
    # Populated rows compare equal in days-since-1960.
    assert out_ref["dt"].iloc[2] == out_actual["dt"].iloc[2]
    assert out_ref["dt"].iloc[3] == out_actual["dt"].iloc[3]


def test_entirely_blank_ref_column_skipped() -> None:
    """ref non-numeric but entirely blank → len(non_blank)==0 continue, unchanged."""
    ref = pd.DataFrame({"dt": ["", "", ""]})
    actual = pd.DataFrame({"dt": [1, 2, 3]})
    ref_dtype = ref["dt"].dtype
    actual_dtype = actual["dt"].dtype

    out_ref, out_actual = _coerce_sas_date_columns(ref, actual)

    assert out_ref["dt"].dtype == ref_dtype
    assert out_actual["dt"].dtype == actual_dtype


def test_non_date_string_column_left_unchanged() -> None:
    """ref non-date strings (parseable<0.8), actual numeric → unchanged dtypes."""
    ref = pd.DataFrame({"arm": ["PLACEBO", "DRUG A", "DRUG B", "PLACEBO"]})
    actual = pd.DataFrame({"arm": [0, 1, 2, 0]})
    ref_dtype = ref["arm"].dtype
    actual_dtype = actual["arm"].dtype

    out_ref, out_actual = _coerce_sas_date_columns(ref, actual)

    assert out_ref["arm"].dtype == ref_dtype
    assert out_actual["arm"].dtype == actual_dtype
    assert out_ref["arm"].tolist() == ["PLACEBO", "DRUG A", "DRUG B", "PLACEBO"]


def test_id_coercion_branch_coerces_actual_to_numeric() -> None:
    """ref=numeric, actual=numeric-strings (F61 IDs) → actual coerced to numeric."""
    ref = pd.DataFrame({"subjid": [1001, 1002, 1003]})
    actual = pd.DataFrame({"subjid": ["1001", "1002", "1003"]})

    assert not pd.api.types.is_numeric_dtype(actual["subjid"])

    out_ref, out_actual = _coerce_sas_date_columns(ref, actual)

    assert pd.api.types.is_numeric_dtype(out_ref["subjid"])
    assert pd.api.types.is_numeric_dtype(out_actual["subjid"])
    assert out_actual["subjid"].tolist() == [1001.0, 1002.0, 1003.0]


def test_id_coercion_branch_entirely_blank_actual_skipped() -> None:
    """ref=numeric, actual non-numeric but entirely blank → continue, unchanged."""
    ref = pd.DataFrame({"subjid": [1, 2, 3]})
    actual = pd.DataFrame({"subjid": ["", "", ""]})
    actual_dtype = actual["subjid"].dtype

    _out_ref, out_actual = _coerce_sas_date_columns(ref, actual)

    assert out_actual["subjid"].dtype == actual_dtype


def test_non_numeric_string_actual_left_unchanged() -> None:
    """ref=numeric, actual genuine strings (numeric_frac<0.8) → unchanged."""
    ref = pd.DataFrame({"code": [1, 2, 3, 4]})
    actual = pd.DataFrame({"code": ["alpha", "beta", "gamma", "delta"]})
    actual_dtype = actual["code"].dtype

    _out_ref, out_actual = _coerce_sas_date_columns(ref, actual)

    assert out_actual["code"].dtype == actual_dtype
    assert out_actual["code"].tolist() == ["alpha", "beta", "gamma", "delta"]


def test_column_missing_from_actual_skipped() -> None:
    """A ref column absent from actual is skipped (col not in actual continue)."""
    ref = pd.DataFrame({"dt": _DATE_STRINGS, "extra": ["x", "y"]})
    actual = pd.DataFrame({"dt": _DATE_SAS_DAYS})

    out_ref, out_actual = _coerce_sas_date_columns(ref, actual)

    assert "extra" in out_ref.columns
    assert "extra" not in out_actual.columns
