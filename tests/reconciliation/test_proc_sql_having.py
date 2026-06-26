"""Reconciliation test — PROC SQL with GROUP BY / HAVING.

Extracted from data/medium_test/sas_pharma_sandbox/sas/05_build_adam_adsl.sas.

Regression guard: PROC SQL containing a HAVING clause must be classified as
PROC_SQL, produce the correct output table, and be ordered before any consumer.
"""

from __future__ import annotations

import pytest
from src.worker.engine.models import BlockType
from src.worker.engine.parser import SASParser

_AESUM_SAS = """
proc sql;
    create table work.aesum as
    select  USUBJID,
            min(AESTDT) as FIRSTAEDT format=yymmdd10.,
            max(AESEV)  as MAXAEGR
    from sdtm.ae
    group by USUBJID
    having count(*) >= 1;
quit;

proc sort data=work.aesum; by USUBJID; run;
"""


@pytest.mark.reconciliation
def test_proc_sql_having_classified_as_proc_sql() -> None:
    """PROC SQL with HAVING must be classified as PROC_SQL."""
    result = SASParser().parse({"05_build_adam_adsl.sas": _AESUM_SAS})

    sql_blocks = [b for b in result.blocks if b.block_type == BlockType.PROC_SQL]
    assert sql_blocks, f"Expected a PROC_SQL block; got: {[b.block_type for b in result.blocks]}"


@pytest.mark.reconciliation
def test_proc_sql_having_produces_aesum() -> None:
    """PROC SQL CREATE TABLE with HAVING must register work.aesum as output."""
    result = SASParser().parse({"05_build_adam_adsl.sas": _AESUM_SAS})

    all_outputs = {ds.lower() for b in result.blocks for ds in b.output_datasets}
    assert any("aesum" in ds for ds in all_outputs), (
        f"Expected 'aesum' in output datasets but got: {all_outputs}"
    )


@pytest.mark.reconciliation
def test_proc_sql_having_before_sort_consumer() -> None:
    """PROC SQL producing aesum must be ordered before the PROC SORT consuming it."""
    result = SASParser().parse({"05_build_adam_adsl.sas": _AESUM_SAS})

    block_order = {id(b): i for i, b in enumerate(result.blocks)}

    sql_block = next(
        (
            b
            for b in result.blocks
            if b.block_type == BlockType.PROC_SQL
            and any("aesum" in ds.lower() for ds in b.output_datasets)
        ),
        None,
    )
    sort_block = next(
        (b for b in result.blocks if b.block_type == BlockType.PROC_SORT),
        None,
    )

    if sql_block and sort_block:
        assert block_order[id(sql_block)] < block_order[id(sort_block)], (
            "PROC SQL producing aesum must precede the PROC SORT that consumes it"
        )


@pytest.mark.reconciliation
def test_having_clause_preserved_in_raw_sas() -> None:
    """The HAVING clause must be preserved verbatim in the PROC_SQL block raw_sas."""
    result = SASParser().parse({"05_build_adam_adsl.sas": _AESUM_SAS})

    sql_block = next(
        (b for b in result.blocks if b.block_type == BlockType.PROC_SQL),
        None,
    )
    assert sql_block is not None
    assert "having" in sql_block.raw_sas.lower(), "HAVING clause must be preserved in raw_sas"
