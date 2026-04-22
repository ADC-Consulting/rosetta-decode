"""Tests for TranslationRouter, _ProcSortHelper, and StubGenerator."""

from unittest.mock import MagicMock

import pytest
from src.worker.engine.models import (
    BlockPlan,
    BlockRisk,
    BlockType,
    JobContext,
    SASBlock,
    TranslationStrategy,
)
from src.worker.engine.router import TranslationRouter, _ProcSortHelper
from src.worker.engine.stub_generator import StubGenerator

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_block(
    block_type: BlockType,
    raw_sas: str = "PROC SORT DATA=work; BY var1; RUN;",
    input_datasets: list[str] | None = None,
    untranslatable_reason: str | None = None,
) -> SASBlock:
    return SASBlock(
        block_type=block_type,
        source_file="test.sas",
        start_line=1,
        end_line=5,
        raw_sas=raw_sas,
        input_datasets=input_datasets or [],
        untranslatable_reason=untranslatable_reason,
    )


def _make_router() -> tuple[TranslationRouter, MagicMock, MagicMock, StubGenerator]:
    data_step_agent = MagicMock()
    proc_agent = MagicMock()
    stub_generator = StubGenerator()
    router = TranslationRouter(
        data_step_agent=data_step_agent,
        proc_agent=proc_agent,
        stub_generator=stub_generator,
    )
    return router, data_step_agent, proc_agent, stub_generator


# ── Router routing tests ───────────────────────────────────────────────────────


def test_routes_data_step() -> None:
    router, data_step_agent, _, _ = _make_router()
    # Use a complex DATA step (IF statement) to bypass _SimpleCopyHelper
    block = _make_block(BlockType.DATA_STEP, raw_sas="DATA out; SET in; IF flag = 1; RUN;")
    assert router.route(block) is data_step_agent


def test_routes_proc_sql() -> None:
    router, _, proc_agent, _ = _make_router()
    block = _make_block(BlockType.PROC_SQL)
    assert router.route(block) is proc_agent


def test_routes_proc_sort() -> None:
    router, _, proc_agent, _ = _make_router()
    block = _make_block(BlockType.PROC_SORT)
    result = router.route(block)
    assert isinstance(result, _ProcSortHelper)
    assert result is not proc_agent


def test_routes_untranslatable() -> None:
    router, _, _, stub_generator = _make_router()
    block = _make_block(BlockType.UNTRANSLATABLE)
    assert router.route(block) is stub_generator


def test_unknown_block_type_routes_to_generic_or_stub() -> None:
    """An unrecognised block_type should route to generic_proc or stub, not raise."""
    router, _, _, stub_generator = _make_router()
    block = _make_block(BlockType.DATA_STEP)
    # Forcibly set an invalid block_type value via object.__setattr__ to bypass Pydantic
    invalid_block = block.model_copy(update={"block_type": "TOTALLY_UNKNOWN"})
    # With no generic_proc_agent injected, falls back to stub
    result = router.route(invalid_block)
    assert result is stub_generator


# ── StubGenerator tests ───────────────────────────────────────────────────────


def test_stub_generator_output() -> None:
    block = _make_block(
        BlockType.UNTRANSLATABLE, untranslatable_reason="PROC TABULATE not supported"
    )
    result = StubGenerator().generate(block)
    lines = result.python_code.splitlines()
    assert len(lines) == 3
    assert lines[0] == "# SAS-UNTRANSLATABLE: PROC TABULATE not supported"
    assert lines[1] == "# TODO: manual review required"
    assert lines[2] == "# SAS: test.sas:1"
    assert result.is_untranslatable is True


def test_stub_reason_missing() -> None:
    block = _make_block(BlockType.UNTRANSLATABLE, untranslatable_reason=None)
    result = StubGenerator().generate(block)
    assert result.python_code.startswith("# SAS-UNTRANSLATABLE: unsupported construct")
    assert result.is_untranslatable is True


# ── _ProcSortHelper tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_proc_sort_helper_by_clause() -> None:
    raw = "PROC SORT DATA=work; BY var1 DESCENDING var2; RUN;"
    block = _make_block(BlockType.PROC_SORT, raw_sas=raw, input_datasets=["work"])
    ctx = JobContext(
        source_files={},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        blocks=[],
        generated=[],
    )
    helper = _ProcSortHelper()
    result = await helper.translate(block, ctx)
    assert "ascending=[True, False]" in result.python_code
    assert result.is_untranslatable is False


@pytest.mark.asyncio
async def test_proc_sort_helper_out_dataset() -> None:
    raw = "PROC SORT DATA=source OUT=work2; BY var1; RUN;"
    block = _make_block(BlockType.PROC_SORT, raw_sas=raw, input_datasets=["source"])
    ctx = JobContext(
        source_files={},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        blocks=[],
        generated=[],
    )
    helper = _ProcSortHelper()
    result = await helper.translate(block, ctx)
    assert result.python_code.splitlines()[1].startswith("work2 = source.sort_values(")


# ── Strategy-based routing tests ─────────────────────────────────────────────


def _make_block_plan(strategy: TranslationStrategy) -> BlockPlan:
    detected: list[str] = ["manual_flag"] if strategy == TranslationStrategy.MANUAL else []
    return BlockPlan(
        block_id="test.sas:1",
        source_file="test.sas",
        start_line=1,
        block_type="DATA_STEP",
        strategy=strategy,
        risk=BlockRisk.LOW,
        rationale="test",
        estimated_effort="low",
        detected_features=detected,
    )


def test_routes_manual_strategy_to_stub() -> None:
    router, _, _, stub_generator = _make_router()
    block = _make_block(BlockType.DATA_STEP, raw_sas="DATA out; SET in; IF flag = 1; RUN;")
    block_plan = _make_block_plan(TranslationStrategy.MANUAL)
    assert router.route(block, block_plan=block_plan) is stub_generator


def test_routes_manual_ingestion_strategy_to_stub() -> None:
    router, _, _, stub_generator = _make_router()
    block = _make_block(BlockType.DATA_STEP, raw_sas="DATA out; SET in; IF flag = 1; RUN;")
    block_plan = _make_block_plan(TranslationStrategy.MANUAL_INGESTION)
    assert router.route(block, block_plan=block_plan) is stub_generator


def test_routes_skip_strategy_to_stub() -> None:
    router, _, _, stub_generator = _make_router()
    block = _make_block(BlockType.DATA_STEP, raw_sas="DATA out; SET in; IF flag = 1; RUN;")
    block_plan = _make_block_plan(TranslationStrategy.SKIP)
    assert router.route(block, block_plan=block_plan) is stub_generator


@pytest.mark.asyncio
async def test_proc_sort_provenance() -> None:
    raw = "PROC SORT DATA=ds; BY col; RUN;"
    block = _make_block(BlockType.PROC_SORT, raw_sas=raw, input_datasets=["ds"])
    ctx = JobContext(
        source_files={},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        blocks=[],
        generated=[],
    )
    helper = _ProcSortHelper()
    result = await helper.translate(block, ctx)
    assert "# SAS: test.sas:1" in result.python_code
