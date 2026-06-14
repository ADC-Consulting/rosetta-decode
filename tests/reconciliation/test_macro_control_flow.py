"""Reconciliation test for F59 — control-flow macro expansion through the parser.

Regression guard for the NameError: name 'adsl_age' is not defined failure that
occurred when a control-flow macro (%if/%do/%return guard) was called but left
unexpanded, so no block produced work.adsl_age and the downstream PROC SORT
consumer crashed. After F59 the call expands to a real DATA step that produces
the dataset before its consumer. Analogous to the F57 'dose' guard.
"""

from __future__ import annotations

import pytest
from src.worker.engine.models import BlockType
from src.worker.engine.parser import SASParser

_MACRO_SAS = """
%macro m_derive_age_group(in=, out=, agevar=AGE, grpvar=AGEGR1);
    %if %length(&in) = 0 %then %do;
        %put ERROR: m_derive_age_group requires IN= dataset.;
        %return;
    %end;
    data &out;
        set &in;
        length &grpvar $8;
        &grpvar = put(&agevar, agegr1f.);
    run;
%mend m_derive_age_group;
"""

_CALLER_SAS = """
data work.adsl_pre;
    set sdtm.dm;
run;

%m_derive_age_group(in=work.adsl_pre, out=work.adsl_age, agevar=AGE, grpvar=AGEGR1);

proc sort data=work.adsl_age; by USUBJID; run;
"""


@pytest.mark.reconciliation
def test_control_flow_macro_expansion_produces_adsl_age() -> None:
    """Control-flow macro call must expand so work.adsl_age is produced before proc sort."""
    files = {
        "macros/m_derive_age_group.sas": _MACRO_SAS,
        "05_build.sas": _CALLER_SAS,
    }

    result = SASParser().parse(files)

    # At least one block must produce a dataset whose name ends in adsl_age
    # (work.adsl_age or work_adsl_age forms), proving the macro CALL expanded
    # into a real DATA step.
    output_datasets = {ds for block in result.blocks for ds in block.output_datasets}
    assert any(ds.lower().endswith("adsl_age") for ds in output_datasets), (
        f"Expected a block producing 'adsl_age' but got output_datasets: {output_datasets}"
    )

    # The proc sort block must exist (consumes adsl_age)
    sort_blocks = [
        b
        for b in result.blocks
        if b.block_type == BlockType.PROC_SORT or "sort" in b.raw_sas.lower()
    ]
    assert sort_blocks, "Expected a PROC SORT block consuming adsl_age"

    # Topo order: adsl_age-producing block comes before the consuming sort block
    block_order = {id(b): i for i, b in enumerate(result.blocks)}
    producer = next(
        b for b in result.blocks if any(ds.lower().endswith("adsl_age") for ds in b.output_datasets)
    )
    consumer = sort_blocks[0]
    assert block_order[id(producer)] < block_order[id(consumer)], (
        "Producer of work.adsl_age must be ordered before the PROC SORT that consumes it. "
        f"producer index={block_order[id(producer)]}, "
        f"consumer index={block_order[id(consumer)]}"
    )
