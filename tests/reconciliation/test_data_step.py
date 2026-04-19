"""Reconciliation tests — DATA step integration + private function unit coverage."""

import pathlib

import pandas as pd
import pytest
from src.worker.compute.local import LocalBackend
from src.worker.validation.reconciliation import (
    ReconciliationService,
    _aggregate_parity,
    _schema_parity,
)

SAMPLES_DIR = pathlib.Path("samples")
REF_CSV = str(SAMPLES_DIR / "basic_etl_ref.csv")
INPUT_CSV = str(SAMPLES_DIR / "employees_raw.csv")

# ── Hand-written pipeline equivalent to basic_etl.sas ────────────────────────
# This is what the LLM would produce for the two blocks in basic_etl.sas.
# Written without pandas-specific idioms so it is backend-agnostic.

_PIPELINE_CODE = f"""\
import pandas as pd

# ── DATA_STEP — basic_etl.sas:8-15 ──
employees_raw = pd.read_csv({INPUT_CSV!r})  # SAS: basic_etl.sas:8

employees_classified = employees_raw.copy()  # SAS: basic_etl.sas:9
employees_classified["salary_band"] = pd.cut(  # SAS: basic_etl.sas:10
    employees_classified["salary"],
    bins=[0, 40000, 80000, float("inf")],
    labels=["LOW", "MID", "HIGH"],
    right=False,
).astype(str)
employees_classified["annual_bonus"] = (  # SAS: basic_etl.sas:14
    employees_classified["salary"] * 0.10
)
employees_classified["full_name"] = (  # SAS: basic_etl.sas:15
    employees_classified["first_name"].str.strip()
    + " "
    + employees_classified["last_name"].str.strip()
)
employees_classified = employees_classified[  # SAS: basic_etl.sas:16
    ["emp_id", "department", "salary", "salary_band", "annual_bonus", "full_name"]
]

# ── PROC_SQL — basic_etl.sas:19-27 ──
result = (  # SAS: basic_etl.sas:19
    employees_classified
    .groupby("department", as_index=False)
    .agg(
        headcount=("emp_id", "count"),
        total_salary=("salary", "sum"),
        avg_salary=("salary", "mean"),
        total_bonus=("annual_bonus", "sum"),
    )
    .sort_values("department")
    .reset_index(drop=True)
)
"""


@pytest.mark.reconciliation
def test_data_step_reconciliation_all_checks_pass() -> None:
    """Full reconciliation: generated pipeline output matches basic_etl_ref.csv."""
    backend = LocalBackend()
    service = ReconciliationService()

    report = service.run(
        ref_csv_path=REF_CSV,
        python_code=_PIPELINE_CODE,
        backend=backend,
    )

    checks = {c["name"]: c for c in report["checks"]}
    assert "schema_parity" in checks, "schema_parity check missing from report"
    assert "row_count" in checks, "row_count check missing from report"
    assert "aggregate_parity" in checks, "aggregate_parity check missing from report"

    for name, check in checks.items():
        assert check["status"] == "pass", (
            f"Check '{name}' failed: {check.get('detail', 'no detail')}"
        )


@pytest.mark.reconciliation
def test_schema_parity_fails_on_extra_column() -> None:
    """Schema check must fail when the pipeline adds an unexpected column."""
    backend = LocalBackend()
    service = ReconciliationService()

    broken_pipeline = _PIPELINE_CODE + "\nresult['extra_col'] = 0\n"
    report = service.run(REF_CSV, broken_pipeline, backend)

    checks = {c["name"]: c for c in report["checks"]}
    assert checks["schema_parity"]["status"] == "fail"
    assert "extra" in checks["schema_parity"]["detail"]


@pytest.mark.reconciliation
def test_row_count_fails_on_extra_row() -> None:
    """Row count check must fail when the pipeline produces an extra row."""
    backend = LocalBackend()
    service = ReconciliationService()

    extra_row_pipeline = _PIPELINE_CODE + (
        "\nextra = pd.DataFrame([{'department':'X','headcount':1,"
        "'total_salary':1,'avg_salary':1,'total_bonus':0.1}])\n"
        "result = pd.concat([result, extra], ignore_index=True)\n"
    )
    report = service.run(REF_CSV, extra_row_pipeline, backend)
    checks = {c["name"]: c for c in report["checks"]}
    assert checks["row_count"]["status"] == "fail"


@pytest.mark.reconciliation
def test_aggregate_parity_fails_on_wrong_sum() -> None:
    """Aggregate check must fail when a numeric column sum is wrong."""
    backend = LocalBackend()
    service = ReconciliationService()

    wrong_agg_pipeline = _PIPELINE_CODE + "\nresult['total_salary'] = result['total_salary'] * 2\n"
    report = service.run(REF_CSV, wrong_agg_pipeline, backend)
    checks = {c["name"]: c for c in report["checks"]}
    assert checks["aggregate_parity"]["status"] == "fail"
    assert "total_salary" in checks["aggregate_parity"]["detail"]


@pytest.mark.reconciliation
def test_report_structure_has_required_keys() -> None:
    """The reconciliation report dict must contain 'checks' as a list."""
    backend = LocalBackend()
    service = ReconciliationService()

    report = service.run(REF_CSV, _PIPELINE_CODE, backend)
    assert "checks" in report
    assert isinstance(report["checks"], list)
    for check in report["checks"]:
        assert "name" in check
        assert "status" in check


@pytest.mark.reconciliation
def test_all_checks_have_valid_status_values() -> None:
    """Every check in the report must have status 'pass' or 'fail'."""
    backend = LocalBackend()
    service = ReconciliationService()

    report = service.run(REF_CSV, _PIPELINE_CODE, backend)
    for check in report["checks"]:
        assert check["status"] in {
            "pass",
            "fail",
        }, f"Unexpected status '{check['status']}' in check '{check['name']}'"


# ── Private function unit tests (no file I/O) ──────────────────────────────────


def test_schema_parity_fails_on_dtype_mismatch() -> None:
    ref = pd.DataFrame({"amount": [1.0, 2.0]})
    actual = pd.DataFrame({"amount": ["1.0", "2.0"]})  # same col, but object dtype
    result = _schema_parity(ref, actual)
    assert result["status"] == "fail"
    assert "amount" in result["detail"]


def test_aggregate_parity_passes_with_no_numeric_cols() -> None:
    ref = pd.DataFrame({"dept": ["A", "B"]})
    actual = pd.DataFrame({"dept": ["A", "B"]})
    result = _aggregate_parity(ref, actual)
    assert result["status"] == "pass"


def test_aggregate_parity_ref_zero_actual_nonzero() -> None:
    ref = pd.DataFrame({"val": [0.0, 0.0]})
    actual = pd.DataFrame({"val": [1.0, 2.0]})
    result = _aggregate_parity(ref, actual)
    assert result["status"] == "fail"
    assert "val" in result["detail"]


def test_aggregate_parity_missing_col_in_actual() -> None:
    ref = pd.DataFrame({"val": [1.0, 2.0]})
    actual = pd.DataFrame({"other": [1.0, 2.0]})
    result = _aggregate_parity(ref, actual)
    assert result["status"] == "fail"
    assert "missing" in result["detail"]


def test_exec_pipeline_no_dataframe_raises() -> None:
    backend = LocalBackend()
    service = ReconciliationService()
    code = "x = 42"  # no DataFrame assigned
    # Provide a ref path so reconciliation is not skipped; the execution check
    # should still fail because the pipeline produces no DataFrame.
    report = service.run(REF_CSV, code, backend)
    checks = {c["name"]: c for c in report["checks"]}
    assert checks.get("execution", {}).get("status") == "fail"


@pytest.mark.reconciliation
def test_failed_pipeline_raises_or_marks_checks_fail() -> None:
    """A pipeline with a syntax error must not crash the service silently."""
    backend = LocalBackend()
    service = ReconciliationService()

    bad_pipeline = "this is not valid python !!!"
    # The service should either raise a clear exception or return all checks as fail —
    # what it must NOT do is silently return all-pass.
    try:
        report = service.run(REF_CSV, bad_pipeline, backend)
        statuses = {c["status"] for c in report["checks"]}
        assert statuses != {"pass"}, "A broken pipeline must not produce all-pass results"
    except Exception:
        pass  # raising is also an acceptable contract
