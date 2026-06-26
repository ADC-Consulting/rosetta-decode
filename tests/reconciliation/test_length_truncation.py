"""Reconciliation test — LENGTH statement controlling character variable width.

Extracted from data/medium_test/sas_pharma_sandbox/sas/01_build_sdtm_dm.sas.

Regression guard: a DATA step with a multi-variable LENGTH declaration and ISO
date parsing (INPUT with yymmdd10.) must be classified as DATA_STEP and preserve
the LENGTH and INPUT statements in raw_sas.
"""

from __future__ import annotations

import pytest
from src.worker.engine.models import BlockType
from src.worker.engine.parser import SASParser

_DM_SAS = """
proc import datafile="./data/raw/dm_raw.csv"
            out=work.dm_raw dbms=csv replace;
    getnames=yes;
    guessingrows=max;
run;

data sdtm.dm;
    length USUBJID $40 STUDYID $20 SUBJID $8 SITEID $4
           ARM $40 ACTARM $40 SEX $1 RACE $40 AGEU $8 DTHFL $1;
    set work.dm_raw;
    USUBJID = catx('-', STUDYID, SITEID, SUBJID);
    RFSTDT = input(RFSTDTC, yymmdd10.);
    if not missing(DTHDTC) then DTHDT = input(DTHDTC, yymmdd10.);
    format RFSTDT DTHDT yymmdd10.;
    keep USUBJID STUDYID SUBJID SITEID ARM ACTARM SEX RACE AGE AGEU
         RFSTDT DTHDT DTHFL;
run;
"""


@pytest.mark.reconciliation
def test_length_declaration_data_step_classified() -> None:
    """DATA step with multi-var LENGTH must be classified as DATA_STEP."""
    result = SASParser().parse({"01_build_sdtm_dm.sas": _DM_SAS})

    data_blocks = [b for b in result.blocks if b.block_type == BlockType.DATA_STEP]
    assert data_blocks, "Expected at least one DATA_STEP block"

    dm_block = next(
        (b for b in data_blocks if any("dm" in ds.lower() for ds in b.output_datasets)),
        None,
    )
    assert dm_block is not None, (
        f"Expected a DATA_STEP producing sdtm.dm but got: "
        f"{[b.output_datasets for b in data_blocks]}"
    )


@pytest.mark.reconciliation
def test_length_and_input_yymmdd_preserved() -> None:
    """LENGTH declaration and yymmdd10. INPUT must be preserved in raw_sas."""
    result = SASParser().parse({"01_build_sdtm_dm.sas": _DM_SAS})

    dm_block = next(
        (
            b
            for b in result.blocks
            if b.block_type == BlockType.DATA_STEP
            and any("dm" in ds.lower() for ds in b.output_datasets)
        ),
        None,
    )
    assert dm_block is not None

    raw = dm_block.raw_sas.lower()
    assert "length" in raw, "LENGTH statement must appear in raw_sas"
    assert "yymmdd10." in raw, "yymmdd10. date informat must appear in raw_sas"
    assert "input(" in raw, "INPUT() date-parse call must appear in raw_sas"


@pytest.mark.reconciliation
def test_conditional_dthdt_parse_preserved() -> None:
    """The conditional DTHDT parse (if not missing(DTHDTC)) must appear in raw_sas."""
    result = SASParser().parse({"01_build_sdtm_dm.sas": _DM_SAS})

    dm_block = next(
        (
            b
            for b in result.blocks
            if b.block_type == BlockType.DATA_STEP
            and any("dm" in ds.lower() for ds in b.output_datasets)
        ),
        None,
    )
    assert dm_block is not None
    assert "dthdtc" in dm_block.raw_sas.lower(), (
        "Conditional death-date parse must be preserved in raw_sas"
    )
