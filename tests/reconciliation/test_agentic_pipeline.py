"""End-to-end reconciliation test for the agentic pipeline.

Verifies correct routing and stub generation for basic_etl.sas without
calling real LLMs.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from src.worker.engine.models import BlockType, GeneratedBlock, JobContext, SASBlock
from src.worker.engine.parser import SASParser
from src.worker.engine.router import TranslationRouter
from src.worker.engine.stub_generator import StubGenerator

_SAMPLES_DIR = Path(__file__).parent.parent.parent / "samples"
_BASIC_ETL_SAS = _SAMPLES_DIR / "basic_etl.sas"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_context(blocks: list[SASBlock]) -> JobContext:
    return JobContext(
        source_files={"basic_etl.sas": _BASIC_ETL_SAS.read_text()},
        resolved_macros=[],
        dependency_order=["employees_raw", "employees_classified", "dept_summary"],
        risk_flags=[],
        blocks=blocks,
        generated=[],
    )


def _make_generated(block: SASBlock, code: str = "pass") -> GeneratedBlock:
    return GeneratedBlock(source_block=block, python_code=code)


def _make_mock_agent(return_code: str = "pass") -> MagicMock:
    """Return a mock agent whose translate() coroutine returns a GeneratedBlock."""
    agent = MagicMock()

    async def _translate(block: SASBlock, context: JobContext) -> GeneratedBlock:
        return _make_generated(block, return_code)

    agent.translate = _translate
    return agent


def _make_router(
    data_step_code: str = "# data step",
    proc_code: str = "# proc sql",
) -> TranslationRouter:
    """Build a TranslationRouter with mocked LLM agents."""
    return TranslationRouter(
        data_step_agent=_make_mock_agent(data_step_code),
        proc_agent=_make_mock_agent(proc_code),
        stub_generator=StubGenerator(),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.reconciliation
def test_basic_etl_parses_two_blocks() -> None:
    """basic_etl.sas must yield exactly 2 blocks (DATA step + PROC SQL)."""
    source = _BASIC_ETL_SAS.read_text()
    parse_result = SASParser().parse({"basic_etl.sas": source})
    assert len(parse_result.blocks) == 2


@pytest.mark.reconciliation
def test_basic_etl_first_block_is_data_step() -> None:
    """First block in basic_etl.sas must be a DATA_STEP."""
    source = _BASIC_ETL_SAS.read_text()
    blocks = SASParser().parse({"basic_etl.sas": source}).blocks
    assert blocks[0].block_type == BlockType.DATA_STEP


@pytest.mark.reconciliation
def test_basic_etl_second_block_is_proc_sql() -> None:
    """Second block in basic_etl.sas must be PROC_SQL."""
    source = _BASIC_ETL_SAS.read_text()
    blocks = SASParser().parse({"basic_etl.sas": source}).blocks
    assert blocks[1].block_type == BlockType.PROC_SQL


@pytest.mark.reconciliation
@pytest.mark.asyncio
async def test_data_step_routes_to_data_step_agent() -> None:
    """TranslationRouter.route() for DATA_STEP must call the DataStepAgent."""
    data_step_block = SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file="basic_etl.sas",
        start_line=7,
        end_line=16,
        raw_sas="DATA employees_classified; SET employees_raw; RUN;",
        input_datasets=["employees_raw"],
        output_datasets=["employees_classified"],
    )
    router = _make_router(data_step_code="# data_step translation")
    context = _make_context([data_step_block])

    translator = router.route(data_step_block)
    gb = await translator.translate(data_step_block, context)

    assert gb.python_code == "# data_step translation"
    assert not gb.is_untranslatable


@pytest.mark.reconciliation
@pytest.mark.asyncio
async def test_proc_sql_routes_to_proc_agent() -> None:
    """TranslationRouter.route() for PROC_SQL must call the ProcAgent."""
    proc_block = SASBlock(
        block_type=BlockType.PROC_SQL,
        source_file="basic_etl.sas",
        start_line=19,
        end_line=29,
        raw_sas=(
            "PROC SQL; CREATE TABLE dept_summary AS SELECT department"
            " FROM employees_classified; QUIT;"
        ),
        input_datasets=["employees_classified"],
        output_datasets=["dept_summary"],
    )
    router = _make_router(proc_code="# proc_sql translation")
    context = _make_context([proc_block])

    translator = router.route(proc_block)
    gb = await translator.translate(proc_block, context)

    assert gb.python_code == "# proc_sql translation"
    assert not gb.is_untranslatable


@pytest.mark.reconciliation
@pytest.mark.asyncio
async def test_proc_sort_routes_to_inline_helper() -> None:
    """PROC_SORT must be handled inline without calling an LLM agent."""
    sort_block = SASBlock(
        block_type=BlockType.PROC_SORT,
        source_file="basic_etl.sas",
        start_line=32,
        end_line=34,
        raw_sas="PROC SORT DATA=employees_classified; BY department salary; RUN;",
        input_datasets=["employees_classified"],
        output_datasets=["employees_classified"],
    )
    router = _make_router()
    context = _make_context([sort_block])

    translator = router.route(sort_block)
    gb = await translator.translate(sort_block, context)

    assert "sort_values" in gb.python_code
    assert not gb.is_untranslatable


@pytest.mark.reconciliation
@pytest.mark.asyncio
async def test_untranslatable_block_produces_stub() -> None:
    """UNTRANSLATABLE blocks must route to StubGenerator and emit SAS-UNTRANSLATABLE."""
    stub_block = SASBlock(
        block_type=BlockType.UNTRANSLATABLE,
        source_file="basic_etl.sas",
        start_line=40,
        end_line=42,
        raw_sas="PROC DATASETS; ...; RUN;",
        untranslatable_reason="PROC DATASETS not supported",
    )
    router = _make_router()
    context = _make_context([stub_block])

    translator = router.route(stub_block)
    gb = await translator.translate(stub_block, context)

    assert "# SAS-UNTRANSLATABLE" in gb.python_code
    assert "# TODO: manual review required" in gb.python_code
    assert gb.is_untranslatable


@pytest.mark.reconciliation
@pytest.mark.asyncio
async def test_full_basic_etl_routing() -> None:
    """All blocks from basic_etl.sas route correctly without LLM calls."""
    source = _BASIC_ETL_SAS.read_text()
    blocks = SASParser().parse({"basic_etl.sas": source}).blocks
    context = _make_context(blocks)
    router = _make_router()

    block_types_translated = []
    for block in blocks:
        translator = router.route(block)
        gb = await translator.translate(block, context)
        block_types_translated.append((block.block_type, gb.is_untranslatable))

    # DATA_STEP → not untranslatable
    assert (BlockType.DATA_STEP, False) in block_types_translated
    # PROC_SQL → not untranslatable
    assert (BlockType.PROC_SQL, False) in block_types_translated
    # No block should raise
    assert len(block_types_translated) == 2
