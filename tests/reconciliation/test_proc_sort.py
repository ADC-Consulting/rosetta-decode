"""Reconciliation test — PROC SORT pipeline."""

import pathlib

import pytest
from src.worker.compute.local import LocalBackend
from src.worker.validation.reconciliation import ReconciliationService

SAMPLES_DIR = pathlib.Path("samples")
REF_CSV = str(SAMPLES_DIR / "proc_sort_expected.csv")
INPUT_CSV = str(SAMPLES_DIR / "employees_raw.csv")

# Hand-written pipeline equivalent to proc_sort_example.sas
# %LET sort_dept = department → becomes SORT_DEPT constant
_PIPELINE_CODE = f"""\
# Macro constants
SORT_DEPT = "department"  # SAS: proc_sort_example.sas:1

import pandas as pd

# ── DATA_STEP — proc_sort_example.sas:8 ──
employees_raw = pd.read_csv({INPUT_CSV!r})  # SAS: proc_sort_example.sas:8
employees_work = employees_raw.copy()  # SAS: proc_sort_example.sas:9
employees_work["annual_bonus"] = employees_work["salary"] * 0.10  # SAS: proc_sort_example.sas:10

# ── PROC_SORT — proc_sort_example.sas:14 (OUT= present) ──
employees_by_dept = employees_work.sort_values(  # SAS: proc_sort_example.sas:14
    [SORT_DEPT, "salary"], ascending=[True, True]
).reset_index(drop=True)

# ── PROC_SORT — proc_sort_example.sas:19 (in-place, DESCENDING salary) ──
employees_by_dept = employees_by_dept.sort_values(  # SAS: proc_sort_example.sas:19
    "salary", ascending=False
).reset_index(drop=True)

result = employees_by_dept
"""


@pytest.mark.reconciliation
def test_proc_sort_reconciliation_all_checks_pass() -> None:
    """Full reconciliation: PROC SORT pipeline output matches proc_sort_expected.csv."""
    backend = LocalBackend()
    service = ReconciliationService()

    report = service.run(
        ref_csv_path=REF_CSV,
        python_code=_PIPELINE_CODE,
        backend=backend,
    )

    checks = {c["name"]: c for c in report["checks"]}
    assert "schema_parity" in checks
    assert "row_count" in checks
    assert "aggregate_parity" in checks

    for name, check in checks.items():
        assert check["status"] == "pass", (
            f"Check '{name}' failed: {check.get('detail', 'no detail')}"
        )
