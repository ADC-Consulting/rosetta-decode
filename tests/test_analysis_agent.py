"""Unit tests for AnalysisAgent."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.worker.engine.agents.analysis import AnalysisAgent, AnalysisError, AnalysisResult
from src.worker.engine.models import BlockType, MacroVar, SASBlock

# ── Fixtures ──────────────────────────────────────────────────────────────────

SOURCE_FILES: dict[str, str] = {"etl.sas": "%LET dept = SALES;\nDATA work.out; SET work.in; RUN;"}

MACRO_VARS: list[MacroVar] = [
    MacroVar(name="DEPT", raw_value="SALES", source_file="etl.sas", line=1)
]

BLOCKS: list[SASBlock] = [
    SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file="etl.sas",
        start_line=2,
        end_line=2,
        raw_sas="DATA work.out; SET work.in; RUN;",
        input_datasets=["work.in"],
        output_datasets=["work.out"],
    )
]

ANALYSIS_RESULT = AnalysisResult(
    resolved_macros=[MacroVar(name="DEPT", raw_value="SALES", source_file="etl.sas", line=1)],
    dependency_order=["work.in", "work.out"],
    risk_flags=["dynamic dataset name in DATA step"],
)


def _make_run_result(analysis: AnalysisResult) -> MagicMock:
    mock = MagicMock()
    mock.output = analysis
    return mock


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.fixture()
def agent_with_mock() -> tuple[AnalysisAgent, AsyncMock]:
    """Return an AnalysisAgent whose internal _agent.run is mocked."""
    agent = AnalysisAgent()
    mock_run = AsyncMock(return_value=_make_run_result(ANALYSIS_RESULT))
    agent._agent.run = mock_run  # type: ignore[method-assign]
    return agent, mock_run


async def test_analyse_returns_job_context_with_source_files(
    agent_with_mock: tuple[AnalysisAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    ctx = await agent.analyse(SOURCE_FILES, MACRO_VARS, BLOCKS)
    assert ctx.source_files == SOURCE_FILES


async def test_analyse_populates_resolved_macros(
    agent_with_mock: tuple[AnalysisAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    ctx = await agent.analyse(SOURCE_FILES, MACRO_VARS, BLOCKS)
    assert len(ctx.resolved_macros) == 1
    assert ctx.resolved_macros[0].name == "DEPT"
    assert ctx.resolved_macros[0].raw_value == "SALES"


async def test_analyse_populates_dependency_order(
    agent_with_mock: tuple[AnalysisAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    ctx = await agent.analyse(SOURCE_FILES, MACRO_VARS, BLOCKS)
    assert ctx.dependency_order == ["work.in", "work.out"]


async def test_analyse_populates_risk_flags(
    agent_with_mock: tuple[AnalysisAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    ctx = await agent.analyse(SOURCE_FILES, MACRO_VARS, BLOCKS)
    assert "dynamic dataset name in DATA step" in ctx.risk_flags


async def test_analyse_sets_blocks_to_input_blocks(
    agent_with_mock: tuple[AnalysisAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    ctx = await agent.analyse(SOURCE_FILES, MACRO_VARS, BLOCKS)
    assert ctx.blocks == BLOCKS


async def test_analyse_sets_generated_empty_and_reconciliation_none(
    agent_with_mock: tuple[AnalysisAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    ctx = await agent.analyse(SOURCE_FILES, MACRO_VARS, BLOCKS)
    assert ctx.generated == []
    assert ctx.reconciliation is None


async def test_analyse_raises_analysis_error_on_llm_failure() -> None:
    agent = AnalysisAgent()
    agent._agent.run = AsyncMock(side_effect=RuntimeError("LLM timeout"))  # type: ignore[method-assign]

    with pytest.raises(AnalysisError) as exc_info:
        await agent.analyse(SOURCE_FILES, MACRO_VARS, BLOCKS)

    assert "AnalysisAgent failed" in str(exc_info.value)
    assert isinstance(exc_info.value.cause, RuntimeError)
