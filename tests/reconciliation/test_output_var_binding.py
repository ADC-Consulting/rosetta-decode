"""Reconciliation test for the assemble_flat consumed-stub-output guarantee.

Regression guard for the NameError: name 'adsl_age' is not defined failure where
a DATA step was routed to the stub generator (strategy=manual) and emitted only a
# SAS-UNRECOGNIZED comment, never creating work.adsl_age. The downstream in-place
PROC SORT (adsl_age = adsl_age.orderBy(...)) then read an undefined name at runtime.

These tests exercise the codegen safety net directly: CodeGenerator.assemble_flat
must raise CodegenError when an untranslatable (stub) block's output dataset is
consumed by another block, and must assemble cleanly when a stub's output is not
consumed. No live LLM is required — GeneratedBlock objects are constructed by hand.
"""

from __future__ import annotations

import pytest
from src.worker.engine.codegen import CodeGenerator, CodegenError
from src.worker.engine.models import BlockType, GeneratedBlock, SASBlock


def _make_block(
    *,
    python_code: str,
    input_datasets: list[str] | None = None,
    output_datasets: list[str] | None = None,
    is_untranslatable: bool = False,
    block_type: BlockType = BlockType.DATA_STEP,
    start_line: int = 1,
    output_var: str | None = None,
) -> GeneratedBlock:
    """Build a GeneratedBlock for the consumed-stub-output check.

    Args:
        python_code: The translated Python source for the block.
        input_datasets: Datasets the block reads (drives the consumed-stem set).
        output_datasets: Datasets the block writes.
        is_untranslatable: Whether the block is a stub.
        block_type: The originating SAS construct type.
        start_line: 1-based start line of the source block.
        output_var: The output variable the block advertises (may be None).

    Returns:
        A GeneratedBlock wrapping a synthetic SASBlock.
    """
    source = SASBlock(
        block_type=block_type,
        source_file="05_build.sas",
        start_line=start_line,
        end_line=start_line,
        raw_sas="data work.adsl_age; set work.adsl_pre; run;",
        input_datasets=input_datasets or [],
        output_datasets=output_datasets or [],
    )
    return GeneratedBlock(
        source_block=source,
        python_code=python_code,
        output_var=output_var,
        is_untranslatable=is_untranslatable,
    )


@pytest.mark.reconciliation
def test_assemble_flat_raises_when_stub_output_consumed() -> None:
    """A stub whose output is read by a later block must raise CodegenError.

    This is the exact failure mode behind the original NameError: a manual/stub
    DATA step produces work.adsl_age but the downstream in-place sort consumes it.
    """
    stub = _make_block(
        python_code="# SAS-UNRECOGNIZED: unsupported construct",
        output_datasets=["work.adsl_age"],
        is_untranslatable=True,
        block_type=BlockType.UNTRANSLATABLE,
        start_line=47,
    )
    consumer = _make_block(
        python_code=(
            "# SAS: 05_build.sas:54\n"
            "from pyspark.sql import functions as F\n"
            'adsl_age = adsl_age.orderBy(F.col("USUBJID").asc())'
        ),
        input_datasets=["work.adsl_age"],
        output_datasets=["work.adsl_age"],
        block_type=BlockType.PROC_SORT,
        start_line=54,
        output_var="adsl_age",
    )
    with pytest.raises(CodegenError) as exc_info:
        CodeGenerator().assemble_flat([stub, consumer])
    message = str(exc_info.value)
    assert "adsl_age" in message
    assert "05_build.sas:47" in message


@pytest.mark.reconciliation
def test_assemble_flat_passes_when_stub_output_not_consumed() -> None:
    """A stub whose output is read by NO other block assembles cleanly.

    Genuine utility blocks (e.g. assertion macros) may stay untranslatable as
    long as nothing downstream depends on their output.
    """
    stub = _make_block(
        python_code="# SAS-UNRECOGNIZED: unsupported construct",
        output_datasets=["work.assert_log"],
        is_untranslatable=True,
        block_type=BlockType.UNTRANSLATABLE,
        start_line=10,
    )
    translated = _make_block(
        python_code="# SAS: 05_build.sas:20\nadsl_age = adsl_pre.withColumn('agegr1', F.lit('1'))",
        input_datasets=["work.adsl_pre"],
        output_datasets=["work.adsl_age"],
        start_line=20,
        output_var="adsl_age",
    )
    rendered = CodeGenerator().assemble_flat([stub, translated])
    assert isinstance(rendered, str)
    assert "adsl_age =" in rendered


@pytest.mark.reconciliation
def test_assemble_flat_passes_when_consumed_output_is_translated() -> None:
    """A consumed dataset produced by a translated (non-stub) block is fine.

    The check targets stub outputs only — a fully translated block that both
    produces and is consumed must not trip the guard.
    """
    producer = _make_block(
        python_code="# SAS: 05_build.sas:47\nadsl_age = adsl_pre.withColumn('agegr1', F.lit('1'))",
        input_datasets=["work.adsl_pre"],
        output_datasets=["work.adsl_age"],
        start_line=47,
        output_var="adsl_age",
    )
    consumer = _make_block(
        python_code=(
            "# SAS: 05_build.sas:54\n"
            "from pyspark.sql import functions as F\n"
            'adsl_age = adsl_age.orderBy(F.col("USUBJID").asc())'
        ),
        input_datasets=["work.adsl_age"],
        output_datasets=["work.adsl_age"],
        block_type=BlockType.PROC_SORT,
        start_line=54,
        output_var="adsl_age",
    )
    rendered = CodeGenerator().assemble_flat([producer, consumer])
    assert "adsl_age = adsl_age.orderBy(" in rendered
