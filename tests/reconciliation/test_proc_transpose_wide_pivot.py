"""Reconciliation test — PROC TRANSPOSE wide pivot with BY/ID/VAR.

Extracted from data/medium_test/sas_pharma_sandbox/sas/04_build_sdtm_lb.sas.

Regression guard:
- PROC TRANSPOSE must be classified as PROC_TRANSPOSE.
- The OUT= dataset (work.lb_wide) must be registered as an output.
- The preceding DATA step (sdtm.lb) must be ordered before the transpose.
"""

from __future__ import annotations

import pytest
from src.worker.engine.models import BlockType
from src.worker.engine.parser import SASParser

_LB_SAS = """
filename lbcsv "./data/raw/lb_raw.csv" encoding="latin1";

proc import datafile=lbcsv out=work.lb_raw dbms=csv replace;
    getnames=yes;
    guessingrows=max;
run;

data sdtm.lb;
    length USUBJID $40;
    set work.lb_raw;
    USUBJID = catx('-', STUDYID, SITEID, SUBJID);
    LBDT = input(LBDTC, yymmdd10.);
    if missing(LBORRES) then LBSTRESN = .;
    else LBSTRESN = input(LBORRES, best12.);
    format LBDT yymmdd10.;
run;

proc transpose data=sdtm.lb out=work.lb_wide(drop=_NAME_) prefix=LB_;
    by USUBJID VISIT;
    id LBTESTCD;
    var LBSTRESN;
run;
"""


@pytest.mark.reconciliation
def test_proc_transpose_classified_correctly() -> None:
    """PROC TRANSPOSE must be classified as PROC_TRANSPOSE, not PROC_UNKNOWN."""
    result = SASParser().parse({"04_build_sdtm_lb.sas": _LB_SAS})

    transpose_blocks = [b for b in result.blocks if b.block_type == BlockType.PROC_TRANSPOSE]
    assert transpose_blocks, (
        f"Expected a PROC_TRANSPOSE block; got block types: {[b.block_type for b in result.blocks]}"
    )


@pytest.mark.reconciliation
def test_proc_transpose_produces_lb_wide() -> None:
    """PROC TRANSPOSE with OUT= must register lb_wide as an output dataset."""
    result = SASParser().parse({"04_build_sdtm_lb.sas": _LB_SAS})

    all_outputs = {ds.lower() for b in result.blocks for ds in b.output_datasets}
    assert any("lb_wide" in ds for ds in all_outputs), (
        f"Expected 'lb_wide' in output datasets but got: {all_outputs}"
    )


@pytest.mark.reconciliation
def test_lb_data_step_before_transpose() -> None:
    """DATA step producing sdtm.lb must be ordered before the PROC TRANSPOSE consuming it."""
    result = SASParser().parse({"04_build_sdtm_lb.sas": _LB_SAS})

    block_order = {id(b): i for i, b in enumerate(result.blocks)}

    lb_data_block = next(
        (
            b
            for b in result.blocks
            if b.block_type == BlockType.DATA_STEP
            and any("lb" in ds.lower() for ds in b.output_datasets)
        ),
        None,
    )
    transpose_block = next(
        (b for b in result.blocks if b.block_type == BlockType.PROC_TRANSPOSE),
        None,
    )

    if lb_data_block and transpose_block:
        assert block_order[id(lb_data_block)] < block_order[id(transpose_block)], (
            "DATA step producing sdtm.lb must be ordered before PROC TRANSPOSE"
        )


@pytest.mark.reconciliation
def test_missing_value_guard_preserved_in_raw_sas() -> None:
    """The missing(LBORRES) guard and best12. coercion must appear in raw_sas."""
    result = SASParser().parse({"04_build_sdtm_lb.sas": _LB_SAS})

    lb_data_block = next(
        (
            b
            for b in result.blocks
            if b.block_type == BlockType.DATA_STEP
            and any("lb" in ds.lower() for ds in b.output_datasets)
        ),
        None,
    )
    assert lb_data_block is not None

    raw = lb_data_block.raw_sas.lower()
    assert "missing(lborres)" in raw, "missing() guard must be preserved in raw_sas"
    assert "best12." in raw, "best12. numeric coercion must be preserved in raw_sas"
