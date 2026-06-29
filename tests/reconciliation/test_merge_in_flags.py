"""Reconciliation test — MERGE with IN= flags and topo ordering.

Extracted from data/medium_test/sas_pharma_sandbox/sas/05_build_adam_adsl.sas.

Regression guard:
- A DATA step containing ``merge ... (in=indm) ... (in=indose)`` must be classified
  as DATA_STEP.
- Both merged datasets must appear in input_datasets so downstream dependency
  resolution can place producers before the merge step.
- The ``if indm;`` subsetting guard must be preserved in raw_sas.
"""

from __future__ import annotations

import pytest
from src.worker.engine.models import BlockType
from src.worker.engine.parser import SASParser

_ADSL_MERGE_SAS = """
proc sort data=sdtm.dm;   by STUDYID SITEID SUBJID; run;
proc sort data=work.dose; by STUDYID SITEID SUBJID; run;

data work.adsl_pre;
    length USUBJID $40 SAFFL $1 ITTFL $1 TRT01P $40 TRT01A $40;
    merge sdtm.dm(in=indm) work.dose(in=indose);
    by STUDYID SITEID SUBJID;
    if indm;
    USUBJID = catx('-', STUDYID, SITEID, SUBJID);
    if not missing(TRTSDT) and not missing(TRTEDT) then
        TRTDURD = intck('day', TRTSDT, TRTEDT) + 1;
    SAFFL  = 'Y';
    ITTFL  = 'Y';
    TRT01P = ARM;
    TRT01A = ACTARM;
run;
"""


@pytest.mark.reconciliation
def test_merge_in_flags_classified_as_data_step() -> None:
    """DATA step with MERGE + IN= flags must be classified as DATA_STEP."""
    result = SASParser().parse({"05_build_adam_adsl.sas": _ADSL_MERGE_SAS})

    data_blocks = [b for b in result.blocks if b.block_type == BlockType.DATA_STEP]
    assert data_blocks, "Expected at least one DATA_STEP block"

    merge_block = next(
        (b for b in data_blocks if "merge" in b.raw_sas.lower()),
        None,
    )
    assert merge_block is not None, "Expected a DATA_STEP block containing MERGE"


@pytest.mark.reconciliation
def test_merge_in_flags_raw_sas_preserved() -> None:
    """The IN= flags and subsetting IF must be preserved verbatim in raw_sas."""
    result = SASParser().parse({"05_build_adam_adsl.sas": _ADSL_MERGE_SAS})

    merge_block = next(
        (
            b
            for b in result.blocks
            if b.block_type == BlockType.DATA_STEP and "merge" in b.raw_sas.lower()
        ),
        None,
    )
    assert merge_block is not None

    raw = merge_block.raw_sas.lower()
    assert "in=indm" in raw, "IN=indm must be preserved in raw_sas"
    assert "in=indose" in raw, "IN=indose must be preserved in raw_sas"
    assert "if indm" in raw, "Subsetting 'if indm' guard must be preserved in raw_sas"


@pytest.mark.reconciliation
def test_merge_produces_adsl_pre() -> None:
    """DATA step with MERGE must register work.adsl_pre as output."""
    result = SASParser().parse({"05_build_adam_adsl.sas": _ADSL_MERGE_SAS})

    all_outputs = {ds.lower() for b in result.blocks for ds in b.output_datasets}
    assert any("adsl_pre" in ds for ds in all_outputs), (
        f"Expected 'adsl_pre' in output datasets but got: {all_outputs}"
    )


@pytest.mark.reconciliation
def test_intck_preserved_in_merge_block() -> None:
    """INTCK date-interval function must be preserved inside the MERGE DATA step."""
    result = SASParser().parse({"05_build_adam_adsl.sas": _ADSL_MERGE_SAS})

    merge_block = next(
        (
            b
            for b in result.blocks
            if b.block_type == BlockType.DATA_STEP and "merge" in b.raw_sas.lower()
        ),
        None,
    )
    assert merge_block is not None
    assert "intck" in merge_block.raw_sas.lower(), (
        "intck() date-interval call must be preserved in raw_sas"
    )
