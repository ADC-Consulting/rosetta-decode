"""Tests for TranslationRouter, _ProcSortHelper, and StubGenerator."""

from unittest.mock import MagicMock

import pytest
from src.worker.engine.models import BlockType, JobContext, SASBlock
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


def test_unknown_block_type_raises() -> None:
    router, _, _, _ = _make_router()
    block = _make_block(BlockType.DATA_STEP)
    # Forcibly set an invalid block_type value via object.__setattr__ to bypass Pydantic
    invalid_block = block.model_copy(update={"block_type": "TOTALLY_UNKNOWN"})
    with pytest.raises(ValueError, match="Unhandled block type"):
        router.route(invalid_block)


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
