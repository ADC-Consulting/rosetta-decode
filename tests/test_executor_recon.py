"""Unit tests for src/executor/recon.py."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pytest

_EXECUTOR_DIR = str(Path(__file__).parent.parent / "src" / "executor")
if _EXECUTOR_DIR not in sys.path:
    sys.path.insert(0, _EXECUTOR_DIR)

import recon  # type: ignore[import-not-found]  # noqa: E402


def _make_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], df.to_dict("records"))


def test_run_recon_no_ref_paths_returns_empty() -> None:
    """With no reference paths, run_recon returns an empty list."""
    result = recon.run_recon([{"a": 1}], ref_csv_path="", ref_sas7bdat_path="")
    assert result == []


def test_run_recon_all_pass(tmp_path: Path) -> None:
    """Identical DataFrames produce all-pass checks."""
    df = pd.DataFrame({"x": [1, 2, 3], "y": [10.0, 20.0, 30.0]})
    csv_path = tmp_path / "ref.csv"
    df.to_csv(csv_path, index=False)

    checks = recon.run_recon(_make_rows(df), ref_csv_path=str(csv_path), ref_sas7bdat_path="")
    assert len(checks) == 3
    assert all(c["status"] == "pass" for c in checks)


def test_run_recon_row_count_fail(tmp_path: Path) -> None:
    """Mismatched row counts produce a row_count fail."""
    ref_df = pd.DataFrame({"x": [1, 2, 3]})
    csv_path = tmp_path / "ref.csv"
    ref_df.to_csv(csv_path, index=False)

    actual_rows = _make_rows(pd.DataFrame({"x": [1, 2]}))
    checks = recon.run_recon(actual_rows, ref_csv_path=str(csv_path), ref_sas7bdat_path="")
    row_check = next(c for c in checks if c["name"] == "row_count")
    assert row_check["status"] == "fail"


def test_run_recon_schema_parity_fail(tmp_path: Path) -> None:
    """Missing column in actual produces a schema_parity fail."""
    ref_df = pd.DataFrame({"a": [1], "b": [2]})
    csv_path = tmp_path / "ref.csv"
    ref_df.to_csv(csv_path, index=False)

    actual_rows = _make_rows(pd.DataFrame({"a": [1]}))
    checks = recon.run_recon(actual_rows, ref_csv_path=str(csv_path), ref_sas7bdat_path="")
    schema_check = next(c for c in checks if c["name"] == "schema_parity")
    assert schema_check["status"] == "fail"


def test_run_recon_aggregate_parity_fail(tmp_path: Path) -> None:
    """Large numeric difference produces an aggregate_parity fail."""
    ref_df = pd.DataFrame({"val": [100.0, 200.0]})
    csv_path = tmp_path / "ref.csv"
    ref_df.to_csv(csv_path, index=False)

    actual_rows = _make_rows(pd.DataFrame({"val": [1.0, 2.0]}))
    checks = recon.run_recon(actual_rows, ref_csv_path=str(csv_path), ref_sas7bdat_path="")
    agg_check = next(c for c in checks if c["name"] == "aggregate_parity")
    assert agg_check["status"] == "fail"


def test_run_recon_missing_csv_returns_execution_fail() -> None:
    """Non-existent reference CSV returns an execution failure check."""
    checks = recon.run_recon([{"x": 1}], ref_csv_path="/tmp/no_such_file.csv", ref_sas7bdat_path="")
    assert len(checks) == 1
    assert checks[0]["name"] == "execution"
    assert checks[0]["status"] == "fail"


# ── NEW COVERAGE: lines 44, 49, 65, 76-77, 106-109, 112 ──────────────────────


def test_schema_parity_dtype_mismatch_via_direct_call() -> None:
    """Lines 44-49: dtype mismatch check is covered by direct _schema_parity call below."""
    pass  # covered by test_schema_parity_direct_dtype_mismatch


def test_schema_parity_direct_dtype_mismatch() -> None:
    """Lines 40-49: direct call to _schema_parity with dtype mismatch."""
    ref_df = pd.DataFrame({"val": [1.0, 2.0]})
    actual_df = pd.DataFrame({"val": ["a", "b"]})

    result = recon._schema_parity(ref_df, actual_df)
    assert result["status"] == "fail"
    assert "numeric" in result["detail"]


def test_aggregate_parity_ref_zero_actual_nonzero() -> None:
    """Lines 76-77: ref sum is 0 but actual is nonzero → aggregate_parity fail."""
    ref_df = pd.DataFrame({"val": [0.0, 0.0]})
    actual_df = pd.DataFrame({"val": [1.0, 2.0]})

    result = recon._aggregate_parity(ref_df, actual_df)
    assert result["status"] == "fail"
    assert "ref=0" in result["detail"]


def test_load_reference_raises_when_no_paths() -> None:
    """Line 112: _load_reference raises ValueError when both paths are empty."""
    with pytest.raises(ValueError, match="Neither"):
        recon._load_reference("", "")


def test_load_reference_with_sas7bdat_path(tmp_path: Path) -> None:
    """Lines 106-109: _load_reference calls pyreadstat when sas7bdat_path given."""
    from unittest.mock import MagicMock, patch

    fake_df = pd.DataFrame({"a": [1, 2]})
    fake_meta = MagicMock()

    with patch("pyreadstat.read_sas7bdat", return_value=(fake_df, fake_meta)):
        result = recon._load_reference("", str(tmp_path / "fake.sas7bdat"))

    assert list(result.columns) == ["a"]


def test_row_count_pass() -> None:
    """Line 65: _row_count returns pass when counts match."""
    ref_df = pd.DataFrame({"a": [1, 2, 3]})
    actual_df = pd.DataFrame({"a": [4, 5, 6]})
    result = recon._row_count(ref_df, actual_df)
    assert result["status"] == "pass"
