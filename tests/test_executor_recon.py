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
    # schema_parity, row_count, aggregate_parity, row_hash_diff (F15)
    assert len(checks) == 4
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


# ── F15: row_hash_diff (executor mirror) ─────────────────────────────────────


def test_run_recon_includes_row_hash_diff(tmp_path: Path) -> None:
    """run_recon appends a row_hash_diff check (passes on identical frames)."""
    df = pd.DataFrame({"id": ["a", "b"], "amount": [1.0, 2.0]})
    csv_path = tmp_path / "ref.csv"
    df.to_csv(csv_path, index=False)

    checks = recon.run_recon(_make_rows(df), ref_csv_path=str(csv_path), ref_sas7bdat_path="")
    rhd = next(c for c in checks if c["name"] == "row_hash_diff")
    assert rhd["status"] == "pass"


def test_run_recon_row_hash_diff_fail_with_config(tmp_path: Path) -> None:
    """Executor parity: a row-level mismatch fails via run_recon with recon_config."""
    ref_df = pd.DataFrame({"id": ["a", "b"], "amount": [100.0, 200.0]})
    csv_path = tmp_path / "ref.csv"
    ref_df.to_csv(csv_path, index=False)

    actual_rows = _make_rows(pd.DataFrame({"id": ["a", "b"], "amount": [100.0, 999.0]}))
    checks = recon.run_recon(
        actual_rows,
        ref_csv_path=str(csv_path),
        ref_sas7bdat_path="",
        recon_config={"join_keys": ["ID"], "float_tolerance": 0.001},
    )
    rhd = next(c for c in checks if c["name"] == "row_hash_diff")
    assert rhd["status"] == "fail"
    assert "amount" in rhd["detail"]


def test_run_recon_row_hash_diff_float_tolerance(tmp_path: Path) -> None:
    """A numeric delta within the configured tolerance passes row_hash_diff."""
    ref_df = pd.DataFrame({"id": ["a"], "amount": [1000.0]})
    csv_path = tmp_path / "ref.csv"
    ref_df.to_csv(csv_path, index=False)

    actual_rows = _make_rows(pd.DataFrame({"id": ["a"], "amount": [1000.5]}))
    checks = recon.run_recon(
        actual_rows,
        ref_csv_path=str(csv_path),
        ref_sas7bdat_path="",
        recon_config={"join_keys": ["id"], "float_tolerance": 0.001},
    )
    rhd = next(c for c in checks if c["name"] == "row_hash_diff")
    assert rhd["status"] == "pass"


def test_infer_join_keys_executor() -> None:
    """Executor _infer_join_keys picks a unique non-numeric column."""
    ref = pd.DataFrame({"id": ["a", "b", "c"], "val": [1, 2, 3]})
    actual = pd.DataFrame({"id": ["a", "b", "c"], "val": [1, 2, 3]})
    assert recon._infer_join_keys(ref, actual) == ["id"]


def test_row_hash_diff_positional_fallback_executor() -> None:
    """Executor _row_hash_diff falls back to positional comparison with no key."""
    # No column (and no composite) is unique → nothing qualifies as a key.
    ref = pd.DataFrame({"grp": [1, 1], "val": [5, 5]})
    actual = pd.DataFrame({"grp": [1, 1], "val": [5, 99]})
    result = recon._row_hash_diff(ref, actual, join_keys=[], float_tolerance=0.001)
    assert result["status"] == "fail"
    assert "positional comparison" in result["detail"]


def test_run_recon_date_vs_timestamp_format_passes(tmp_path: Path) -> None:
    """Executor parity: date-only ref vs full-timestamp actual must NOT mismatch."""
    ref_df = pd.DataFrame({"id": ["a", "b"], "visitdt": ["2025-06-10", "2025-06-11"]})
    csv_path = tmp_path / "ref.csv"
    ref_df.to_csv(csv_path, index=False)

    actual_rows = _make_rows(
        pd.DataFrame(
            {"id": ["a", "b"], "visitdt": ["2025-06-10T00:00:00.000", "2025-06-11T00:00:00.000"]}
        )
    )
    checks = recon.run_recon(
        actual_rows,
        ref_csv_path=str(csv_path),
        ref_sas7bdat_path="",
        recon_config={"join_keys": ["id"], "float_tolerance": 0.001},
    )
    rhd = next(c for c in checks if c["name"] == "row_hash_diff")
    assert rhd["status"] == "pass"


def test_run_recon_genuinely_different_dates_still_fails(tmp_path: Path) -> None:
    """Executor control: genuinely different dates must still fail row_hash_diff."""
    ref_df = pd.DataFrame({"id": ["a"], "visitdt": ["2025-06-10"]})
    csv_path = tmp_path / "ref.csv"
    ref_df.to_csv(csv_path, index=False)

    actual_rows = _make_rows(pd.DataFrame({"id": ["a"], "visitdt": ["2025-06-11T00:00:00.000"]}))
    checks = recon.run_recon(
        actual_rows,
        ref_csv_path=str(csv_path),
        ref_sas7bdat_path="",
        recon_config={"join_keys": ["id"], "float_tolerance": 0.001},
    )
    rhd = next(c for c in checks if c["name"] == "row_hash_diff")
    assert rhd["status"] == "fail"
    assert "visitdt" in rhd["detail"]


# ── F15: validated join-key inference (executor mirror of the bug fix) ───────


@pytest.mark.reconciliation
def test_infer_join_keys_rejects_mostly_null_dthdtc_executor() -> None:
    """The exact bug (executor copy): mostly-null dthdtc rejected; usubjid chosen."""
    ref = pd.DataFrame(
        {
            "usubjid": [f"S-{i}" for i in range(12)],
            "dthdtc": [None] * 11 + ["2025-01-01"],
        }
    )
    actual = ref.copy()
    assert recon._infer_join_keys(ref, actual) == ["usubjid"]


@pytest.mark.reconciliation
def test_row_hash_diff_dthdtc_pass_and_fail_executor() -> None:
    """Sparse dthdtc + real usubjid: identical passes, single change fails (executor)."""
    ref = pd.DataFrame(
        {
            "usubjid": [f"S-{i}" for i in range(12)],
            "dthdtc": [None] * 11 + ["2025-01-01"],
            "age": list(range(20, 32)),
        }
    )
    passed = recon._row_hash_diff(ref, ref.copy(), join_keys=[], float_tolerance=0.001)
    assert passed["status"] == "pass"

    changed = ref.copy()
    changed.loc[3, "age"] = 999
    failed = recon._row_hash_diff(ref, changed, join_keys=[], float_tolerance=0.001)
    assert failed["status"] == "fail"
    assert "usubjid='S-3'" in failed["detail"]


@pytest.mark.reconciliation
def test_infer_join_keys_composite_executor() -> None:
    """No single unique column, but siteid+subjid is unique → composite (executor)."""
    # No single column is unique (each repeats); only siteid+subjid is unique.
    ref = pd.DataFrame(
        {
            "siteid": ["01", "01", "02", "02"],
            "subjid": ["1", "2", "1", "2"],
            "val": [10, 20, 10, 20],
        }
    )
    keys = recon._infer_join_keys(ref, ref.copy())
    assert set(keys) == {"siteid", "subjid"}


def test_infer_join_keys_no_usable_key_returns_empty_executor() -> None:
    """No fully-populated unique column → [] (positional fallback) in executor."""
    # Fully duplicated rows: no single column and no composite is unique.
    ref = pd.DataFrame({"grp": ["x", "x"], "val": [1, 1]})
    actual = ref.copy()
    assert recon._infer_join_keys(ref, actual) == []


@pytest.mark.reconciliation
def test_infer_join_keys_rejects_unique_but_mostly_null_executor() -> None:
    """A unique-but-mostly-null column is NOT chosen (executor copy)."""
    ref = pd.DataFrame(
        {
            "sparseid": ["only"] + [None] * 9,
            "usubjid": [f"S-{i}" for i in range(10)],
        }
    )
    assert recon._infer_join_keys(ref, ref.copy()) == ["usubjid"]


def test_explicit_nonunique_key_surfaces_warning_executor() -> None:
    """An explicit non-unique key is flagged (executor copy)."""
    ref = pd.DataFrame({"grp": ["x", "x"], "val": [1, 2]})
    result = recon._compare_keyed(ref, ref.copy(), ["grp"], 0.001)
    assert result.get("key_warning")
    assert "non-unique" in result["key_warning"]
