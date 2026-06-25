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
    assert lines[0] == "# SAS-UNRECOGNIZED: PROC TABULATE not supported"
    assert lines[1] == "# TODO: manual review required"
    assert lines[2] == "# SAS: test.sas:1"
    assert result.is_untranslatable is True


def test_stub_reason_missing() -> None:
    block = _make_block(BlockType.UNTRANSLATABLE, untranslatable_reason=None)
    result = StubGenerator().generate(block)
    assert result.python_code.startswith("# SAS-UNRECOGNIZED: unsupported construct")
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
    assert 'F.col("var1").asc()' in result.python_code
    assert 'F.col("var2").desc()' in result.python_code
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
    assert "work2 = source.orderBy(" in result.python_code


@pytest.mark.asyncio
async def test_proc_sort_helper_inplace_sets_output_var() -> None:
    """In-place PROC SORT must advertise output_var so codegen's binding check passes.

    Regression guard for the NameError: an in-place sort emits
    ``adsl_age = adsl_age.orderBy(...)`` and must report output_var=adsl_age,
    matching the variable its python_code binds (fix #3).
    """
    raw = "PROC SORT DATA=work.adsl_age; BY USUBJID; RUN;"
    block = _make_block(BlockType.PROC_SORT, raw_sas=raw, input_datasets=["work.adsl_age"])
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
    assert result.output_var == "adsl_age"
    # The emitted code must bind the same variable it advertises.
    assert f"{result.output_var} =" in result.python_code


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


def test_proc_print_routes_to_generic_proc_agent() -> None:
    """PROC_PRINT blocks must route to GenericProcAgent, not StubGenerator."""
    data_step_agent = MagicMock()
    proc_agent = MagicMock()
    stub_generator = StubGenerator()
    generic_proc_agent = MagicMock()
    router = TranslationRouter(
        data_step_agent=data_step_agent,
        proc_agent=proc_agent,
        stub_generator=stub_generator,
        generic_proc_agent=generic_proc_agent,
    )
    block = _make_block(BlockType.PROC_PRINT, raw_sas="PROC PRINT DATA=work; RUN;")
    result = router.route(block)
    assert result is generic_proc_agent
    assert result is not stub_generator


def test_manual_strategies_set() -> None:
    """_MANUAL_STRATEGIES must equal frozenset({'manual'})."""
    from src.backend.api.routes.jobs import _MANUAL_STRATEGIES

    assert frozenset({"manual"}) == _MANUAL_STRATEGIES


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


# ── _ProcSortHelper._parse_by_clause uncovered branches (lines 66, 76) ──────


@pytest.mark.asyncio
async def test_proc_sort_helper_no_by_clause_returns_empty() -> None:
    """_parse_by_clause returns empty lists when no BY clause is present (line 66)."""
    raw = "PROC SORT DATA=ds; RUN;"  # no BY clause
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
    # With no BY clause, by=[] and ascending=[] — just assert no crash
    assert result.is_untranslatable is False
    assert "orderBy(" in result.python_code


@pytest.mark.asyncio
async def test_proc_sort_helper_ascending_keyword() -> None:
    """_parse_by_clause handles ASCENDING keyword correctly (line 76)."""
    raw = "PROC SORT DATA=work; BY ASCENDING var1 DESCENDING var2 var3; RUN;"
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
    assert 'F.col("var1").asc()' in result.python_code
    assert 'F.col("var2").desc()' in result.python_code
    assert 'F.col("var3").asc()' in result.python_code


# ── _StrategyStubAdapter (init + translate) ──────────────────────────────────


@pytest.mark.asyncio
async def test_strategy_stub_adapter_init_and_translate() -> None:
    """_StrategyStubAdapter stores stub_generator and delegates to generate() (lines 66, 76)."""
    from src.worker.engine.router import _StrategyStubAdapter

    stub = StubGenerator()
    adapter = _StrategyStubAdapter(stub, strategy="manual")

    assert adapter._stub is stub
    assert adapter._strategy == "manual"

    block = _make_block(BlockType.UNTRANSLATABLE, untranslatable_reason="no equivalent")
    ctx = JobContext(
        source_files={},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        blocks=[],
        generated=[],
    )
    result = await adapter.translate(block, ctx)
    assert result.is_untranslatable is True


# ── _SimpleCopyHelper.translate() branches (lines 173-197) ──────────────────


@pytest.mark.asyncio
async def test_simple_copy_helper_keep_branch() -> None:
    """_SimpleCopyHelper emits .select() with column filter when KEEP is present."""
    from src.worker.engine.router import _SimpleCopyHelper

    raw = "DATA out; SET in; KEEP col1 col2; RUN;"
    block = _make_block(BlockType.DATA_STEP, raw_sas=raw, input_datasets=["in"])
    ctx = JobContext(
        source_files={},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        blocks=[],
        generated=[],
    )
    result = await _SimpleCopyHelper().translate(block, ctx)
    assert ".select(" in result.python_code
    assert "col1" in result.python_code
    assert "col2" in result.python_code


@pytest.mark.asyncio
async def test_simple_copy_helper_drop_branch() -> None:
    """_SimpleCopyHelper emits .drop() when DROP is present (lines 188-192)."""
    from src.worker.engine.router import _SimpleCopyHelper

    raw = "DATA out; SET in; DROP col3; RUN;"
    block = _make_block(BlockType.DATA_STEP, raw_sas=raw, input_datasets=["in"])
    ctx = JobContext(
        source_files={},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        blocks=[],
        generated=[],
    )
    result = await _SimpleCopyHelper().translate(block, ctx)
    assert ".drop(" in result.python_code
    assert "col3" in result.python_code


@pytest.mark.asyncio
async def test_simple_copy_helper_plain_copy() -> None:
    """_SimpleCopyHelper emits direct assignment (no .copy()) for plain SET."""
    from src.worker.engine.router import _SimpleCopyHelper

    raw = "DATA out; SET in; RUN;"
    block = _make_block(BlockType.DATA_STEP, raw_sas=raw, input_datasets=["in"])
    ctx = JobContext(
        source_files={},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        blocks=[],
        generated=[],
    )
    result = await _SimpleCopyHelper().translate(block, ctx)
    assert "out = in  " in result.python_code
    assert ".copy()" not in result.python_code


# ── router.route() simple DATA step returns _simple_copy (line 289) ─────────


def test_routes_simple_data_step_to_simple_copy_helper() -> None:
    """A simple SET+copy DATA step routes to _SimpleCopyHelper, not data_step_agent (line 289)."""
    from src.worker.engine.router import _SimpleCopyHelper

    router, data_step_agent, _, _ = _make_router()
    block = _make_block(BlockType.DATA_STEP, raw_sas="DATA out; SET in; RUN;")
    result = router.route(block)
    assert isinstance(result, _SimpleCopyHelper)
    assert result is not data_step_agent


# ── S-E0: is_simple() allowlist guard against put()/assignment DATA steps ────


def test_put_assignment_data_step_routes_to_agent_not_simple_copy() -> None:
    """A put()-bearing DATA step must route to DataStepAgent, not _SimpleCopyHelper."""
    from src.worker.engine.router import _SimpleCopyHelper

    router, data_step_agent, _, _ = _make_router()
    raw = "data out; set in; length AGEGR1 $8; AGEGR1 = put(AGE, agegr1f.); run;"
    block = _make_block(BlockType.DATA_STEP, raw_sas=raw, input_datasets=["in"])
    result = router.route(block)
    assert result is data_step_agent
    assert not isinstance(result, _SimpleCopyHelper)
    assert _SimpleCopyHelper.is_simple(block) is False


def test_pure_set_keep_data_step_remains_simple() -> None:
    """Regression: a pure SET+KEEP DATA step must still be classified simple."""
    from src.worker.engine.router import _SimpleCopyHelper

    block = _make_block(
        BlockType.DATA_STEP, raw_sas="data out; set in; keep a b; run;", input_datasets=["in"]
    )
    assert _SimpleCopyHelper.is_simple(block) is True


def test_plain_assignment_data_step_not_simple() -> None:
    """A plain assignment (x = a + 1) makes the DATA step non-simple."""
    from src.worker.engine.router import _SimpleCopyHelper

    block = _make_block(
        BlockType.DATA_STEP, raw_sas="data out; set in; x = a + 1; run;", input_datasets=["in"]
    )
    assert _SimpleCopyHelper.is_simple(block) is False


# ── router.route() with non-MANUAL block_plan falls through (lines 283-284) ──


def test_route_translated_strategy_with_block_plan_falls_through_to_block_type() -> None:
    """Non-MANUAL block_plan falls through to block_type dispatch (lines 283-284)."""
    router, _, proc_agent, _ = _make_router()
    block = _make_block(BlockType.PROC_SQL)
    block_plan = BlockPlan(
        block_id="test.sas:1",
        source_file="test.sas",
        start_line=1,
        block_type="PROC_SQL",
        strategy=TranslationStrategy.TRANSLATED,
        risk=BlockRisk.LOW,
        rationale="simple select",
        estimated_effort="low",
        detected_features=[],
    )
    result = router.route(block, block_plan=block_plan)
    assert result is proc_agent


# ── router.route() with MANUAL strategy (lines 283-284) ─────────────────────


def test_route_manual_strategy_returns_stub_generator() -> None:
    """route() with MANUAL block_plan returns stub_generator (lines 283-284)."""
    router, _, _, stub_generator = _make_router()
    block = _make_block(BlockType.DATA_STEP, raw_sas="DATA out; SET in; IF x=1; RUN;")
    block_plan = BlockPlan(
        block_id="test.sas:1",
        source_file="test.sas",
        start_line=1,
        block_type="DATA_STEP",
        strategy=TranslationStrategy.MANUAL,
        risk=BlockRisk.HIGH,
        rationale="manual",
        estimated_effort="high",
        detected_features=["no_py_equiv"],
    )
    result = router.route(block, block_plan=block_plan)
    assert result is stub_generator


# ── Generic PROC routing with and without agent (lines 289, 301, 305) ────────


def test_routes_generic_proc_with_agent_injected() -> None:
    """Generic PROC types route to generic_proc_agent when it is injected (line 299)."""
    data_step_agent = MagicMock()
    proc_agent = MagicMock()
    stub_generator = StubGenerator()
    generic_proc_agent = MagicMock()
    router = TranslationRouter(
        data_step_agent=data_step_agent,
        proc_agent=proc_agent,
        stub_generator=stub_generator,
        generic_proc_agent=generic_proc_agent,
    )
    block = _make_block(BlockType.PROC_IML, raw_sas="PROC IML; RUN;")
    assert router.route(block) is generic_proc_agent


def test_routes_generic_proc_without_agent_falls_back_to_stub() -> None:
    """Generic PROC types route to stub_generator when no agent injected (line 301)."""
    router, _, _, stub_generator = _make_router()
    block = _make_block(BlockType.PROC_IML, raw_sas="PROC IML; RUN;")
    assert router.route(block) is stub_generator


def test_routes_unknown_block_type_with_agent() -> None:
    """Truly unknown block_type routes to generic_proc_agent when injected (line 305)."""
    data_step_agent = MagicMock()
    proc_agent = MagicMock()
    stub_generator = StubGenerator()
    generic_proc_agent = MagicMock()
    router = TranslationRouter(
        data_step_agent=data_step_agent,
        proc_agent=proc_agent,
        stub_generator=stub_generator,
        generic_proc_agent=generic_proc_agent,
    )
    block = _make_block(BlockType.DATA_STEP)
    invalid_block = block.model_copy(update={"block_type": "TOTALLY_UNKNOWN_TYPE"})
    result = router.route(invalid_block)
    assert result is generic_proc_agent
