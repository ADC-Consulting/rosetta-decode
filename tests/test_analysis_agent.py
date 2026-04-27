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


def test_analysis_make_agent_tensorzero_path() -> None:
    """_make_agent() uses TensorZero when tensorzero_gateway_url is set."""
    from unittest.mock import MagicMock, patch

    mock_settings = MagicMock()
    mock_settings.tensorzero_gateway_url = "http://tz:7000"
    mock_settings.azure_openai_endpoint = ""
    mock_settings.llm_model = "anthropic:claude-sonnet-4-6"

    mock_tz_provider = MagicMock()
    mock_model = MagicMock()
    mock_agent = MagicMock()

    with (
        patch("src.worker.engine.agents.analysis.worker_settings", mock_settings),
        patch("src.worker.engine.agents.analysis.OpenAIProvider", return_value=mock_tz_provider),
        patch(
            "src.worker.engine.agents.analysis.OpenAIChatModel", return_value=mock_model
        ) as mock_oai_model,
        patch("src.worker.engine.agents.analysis.Agent", return_value=mock_agent),
    ):
        from src.worker.engine.agents.analysis import _make_agent

        result = _make_agent()

    call_kwargs = mock_oai_model.call_args
    first_arg = call_kwargs.args[0] if call_kwargs.args else ""
    model_name_arg = call_kwargs.kwargs.get("model_name", first_arg)
    assert "tensorzero::" in model_name_arg
    assert result is mock_agent


def test_analysis_make_agent_azure_path() -> None:
    """_make_agent() uses AzureProvider when azure_openai_endpoint is set."""
    from unittest.mock import MagicMock, patch

    mock_settings = MagicMock()
    mock_settings.tensorzero_gateway_url = ""
    mock_settings.azure_openai_endpoint = "https://my.azure.openai.com"
    mock_settings.azure_openai_api_key = "fake-key"
    mock_settings.openai_api_version = "2024-02-01"
    mock_settings.llm_model = "azure:gpt-4o"

    mock_azure_provider = MagicMock()
    mock_model = MagicMock()
    mock_agent = MagicMock()

    with (
        patch("src.worker.engine.agents.analysis.worker_settings", mock_settings),
        patch(
            "src.worker.engine.agents.analysis.AzureProvider", return_value=mock_azure_provider
        ) as mock_az,
        patch("src.worker.engine.agents.analysis.OpenAIChatModel", return_value=mock_model),
        patch("src.worker.engine.agents.analysis.Agent", return_value=mock_agent),
    ):
        from src.worker.engine.agents.analysis import _make_agent

        result = _make_agent()

    mock_az.assert_called_once()
    assert result is mock_agent
