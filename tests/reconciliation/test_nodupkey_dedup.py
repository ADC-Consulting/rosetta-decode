"""Reconciliation test — PROC SORT NODUPKEY deduplication.

Extracted from data/medium_test/sas_pharma_sandbox/sas/02_build_sdtm_ex.sas.

Regression guard: PROC SORT with the NODUPKEY option must produce a separate output
dataset (via OUT=) and must be classified as PROC_SORT — not an unknown block.
The downstream DATA step depends on the deduplicated dataset.
"""

from __future__ import annotations

import pytest
from src.worker.engine.models import BlockType
from src.worker.engine.parser import SASParser

_EX_SAS = """
proc import datafile="./data/raw/ex_raw.csv"
            out=work.ex_raw dbms=csv replace;
    getnames=yes;
    guessingrows=max;
run;

proc sort data=work.ex_raw out=work.ex_dedup nodupkey;
    by STUDYID SUBJID SITEID EXSTDTC EXENDTC EXTRT EXDOSE;
run;

data sdtm.ex;
    length USUBJID $40;
    set work.ex_dedup;
    USUBJID = catx('-', STUDYID, SITEID, SUBJID);
    EXSTDT = input(EXSTDTC, yymmdd10.);
    EXENDT = input(EXENDTC, yymmdd10.);
    format EXSTDT EXENDT yymmdd10.;
run;
"""


@pytest.mark.reconciliation
def test_nodupkey_classified_as_proc_sort() -> None:
    """PROC SORT NODUPKEY must be classified as PROC_SORT."""
    result = SASParser().parse({"02_build_sdtm_ex.sas": _EX_SAS})

    sort_blocks = [b for b in result.blocks if b.block_type == BlockType.PROC_SORT]
    assert sort_blocks, "Expected at least one PROC_SORT block for NODUPKEY step"

    nodupkey_block = next(
        (b for b in sort_blocks if "nodupkey" in b.raw_sas.lower()),
        None,
    )
    assert nodupkey_block is not None, "PROC SORT NODUPKEY block not found in parsed blocks"


@pytest.mark.reconciliation
def test_nodupkey_produces_ex_dedup_output() -> None:
    """PROC SORT NODUPKEY with OUT= must register ex_dedup as an output dataset."""
    result = SASParser().parse({"02_build_sdtm_ex.sas": _EX_SAS})

    all_outputs = {ds.lower() for b in result.blocks for ds in b.output_datasets}
    assert any("ex_dedup" in ds for ds in all_outputs), (
        f"Expected 'ex_dedup' in output datasets but got: {all_outputs}"
    )


@pytest.mark.reconciliation
def test_nodupkey_before_data_step_consumer() -> None:
    """PROC SORT NODUPKEY must be ordered before the DATA step consuming ex_dedup."""
    result = SASParser().parse({"02_build_sdtm_ex.sas": _EX_SAS})

    block_order = {id(b): i for i, b in enumerate(result.blocks)}

    sort_block = next(
        (b for b in result.blocks if b.block_type == BlockType.PROC_SORT),
        None,
    )
    ex_data_block = next(
        (
            b
            for b in result.blocks
            if b.block_type == BlockType.DATA_STEP
            and any("ex" in ds.lower() for ds in b.output_datasets)
        ),
        None,
    )

    if sort_block and ex_data_block:
        assert block_order[id(sort_block)] < block_order[id(ex_data_block)], (
            "PROC SORT NODUPKEY must be ordered before the DATA step consuming ex_dedup"
        )
