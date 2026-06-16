"""Reconciliation test for F57 — cross-block macro expansion and dependency ordering.

Regression guard for the NameError: name 'dose' is not defined failure that
occurred when %m_first_dose expanded into a PROC SQL block producing work.dose,
but the topo-sort placed the PROC SORT consumer before the producer.
"""

from __future__ import annotations

import pytest
from src.worker.engine.models import BlockType
from src.worker.engine.parser import SASParser

_MACRO_SAS = """
%macro m_first_dose(in=, out=);
    proc sql;
        create table &out as
        select min(exstdtc) as rfstdtc
        from &in;
    quit;
%mend m_first_dose;
"""

_CALLER_SAS = """
%m_first_dose(in=sdtm.ex, out=work.dose);

proc sort data=work.dose;
    by usubjid;
run;
"""


@pytest.mark.reconciliation
def test_macro_call_expansion_produces_dose_block() -> None:
    """Macro call %m_first_dose must expand so work.dose is produced before proc sort."""
    files = {
        "macros/m_first_dose.sas": _MACRO_SAS,
        "05_build_adam_adsl.sas": _CALLER_SAS,
    }

    result = SASParser().parse(files)

    # At least one block must have work.dose (or dose) in its output_datasets
    output_datasets = {ds for block in result.blocks for ds in block.output_datasets}
    assert any("dose" in ds.lower() for ds in output_datasets), (
        f"Expected a block producing 'dose' but got output_datasets: {output_datasets}"
    )

    # The proc sort block must exist (consumes dose)
    sort_blocks = [
        b
        for b in result.blocks
        if b.block_type == BlockType.PROC_SORT or "sort" in b.raw_sas.lower()
    ]
    assert sort_blocks, "Expected a PROC SORT block consuming dose"

    # Topo order: dose-producing block comes before dose-consuming sort block
    block_order = {id(b): i for i, b in enumerate(result.blocks)}
    producer = next(
        b for b in result.blocks if any("dose" in ds.lower() for ds in b.output_datasets)
    )
    consumer = sort_blocks[0]
    assert block_order[id(producer)] < block_order[id(consumer)], (
        "Producer of work.dose must be ordered before the PROC SORT that consumes it. "
        f"producer index={block_order[id(producer)]}, "
        f"consumer index={block_order[id(consumer)]}"
    )
