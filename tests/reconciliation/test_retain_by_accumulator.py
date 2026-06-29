"""Reconciliation test — RETAIN + BY + FIRST./LAST. + row-sequence accumulator.

Extracted from data/medium_test/sas_pharma_sandbox/sas/03_build_sdtm_ae.sas.

Regression guard for two patterns that must survive parsing intact:
1. ``RETAIN <var>;`` declares a retained variable — the block must be a DATA_STEP.
2. ``AESEQ + 1;`` is a SAS accumulator (implicit RETAIN + increment) — the parser
   must not drop the block or misclassify it.
"""

from __future__ import annotations

import pytest
from src.worker.engine.models import BlockType
from src.worker.engine.parser import SASParser

_AE_SAS = """
proc import datafile="./data/raw/ae_raw.csv"
            out=work.ae_raw dbms=csv replace;
    getnames=yes;
    guessingrows=max;
run;

proc sort data=work.ae_raw; by STUDYID SITEID SUBJID AESTDTC; run;

data sdtm.ae;
    length USUBJID $40 AESEVC $20;
    retain AESEQ;
    set work.ae_raw;
    by STUDYID SITEID SUBJID AESTDTC;
    if first.SUBJID then AESEQ = 0;
    AESEQ + 1;
    USUBJID = catx('-', STUDYID, SITEID, SUBJID);
    AESTDT = input(AESTDTC, yymmdd10.);
    AESEVC = put(AESEV, aegrf.);
    format AESTDT yymmdd10.;
run;
"""


@pytest.mark.reconciliation
def test_retain_by_first_last_accumulator_produces_data_step() -> None:
    """DATA step with RETAIN + BY + FIRST./LAST. + accumulator must parse as DATA_STEP."""
    result = SASParser().parse({"03_build_sdtm_ae.sas": _AE_SAS})

    data_blocks = [b for b in result.blocks if b.block_type == BlockType.DATA_STEP]
    assert data_blocks, "Expected at least one DATA_STEP block"

    ae_block = next(
        (b for b in data_blocks if any("ae" in ds.lower() for ds in b.output_datasets)),
        None,
    )
    assert ae_block is not None, (
        f"Expected a DATA_STEP producing sdtm.ae but got output_datasets: "
        f"{[b.output_datasets for b in data_blocks]}"
    )


@pytest.mark.reconciliation
def test_retain_block_raw_sas_preserved() -> None:
    """The RETAIN + accumulator source must appear verbatim in block.raw_sas."""
    result = SASParser().parse({"03_build_sdtm_ae.sas": _AE_SAS})

    data_blocks = [b for b in result.blocks if b.block_type == BlockType.DATA_STEP]
    ae_block = next(
        (b for b in data_blocks if any("ae" in ds.lower() for ds in b.output_datasets)),
        None,
    )
    assert ae_block is not None

    raw = ae_block.raw_sas.lower()
    assert "retain" in raw, "RETAIN statement must be preserved in raw_sas"
    assert "first.subjid" in raw, "FIRST.SUBJID must be preserved in raw_sas"
    assert "aeseq + 1" in raw, "Accumulator AESEQ + 1 must be preserved in raw_sas"


@pytest.mark.reconciliation
def test_proc_sort_ae_before_data_step_ae() -> None:
    """PROC SORT on ae_raw must be ordered before the DATA step that consumes it."""
    result = SASParser().parse({"03_build_sdtm_ae.sas": _AE_SAS})

    block_order = {id(b): i for i, b in enumerate(result.blocks)}

    sort_block = next(
        (
            b
            for b in result.blocks
            if b.block_type == BlockType.PROC_SORT
            and any("ae_raw" in ds.lower() for ds in b.input_datasets or [])
        ),
        None,
    )
    ae_data_block = next(
        (
            b
            for b in result.blocks
            if b.block_type == BlockType.DATA_STEP
            and any("ae" in ds.lower() for ds in b.output_datasets)
        ),
        None,
    )

    if sort_block and ae_data_block:
        assert block_order[id(sort_block)] < block_order[id(ae_data_block)], (
            "PROC SORT of ae_raw must come before the DATA step producing sdtm.ae"
        )
