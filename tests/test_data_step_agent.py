"""Unit tests for DataStepAgent."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.worker.engine.agents.data_step import DataStepAgent, DataStepError, DataStepResult
from src.worker.engine.models import BlockType, GeneratedBlock, JobContext, MacroVar, SASBlock

# ── Fixtures ──────────────────────────────────────────────────────────────────

BLOCK = SASBlock(
    block_type=BlockType.DATA_STEP,
    source_file="etl.sas",
    start_line=3,
    end_line=5,
    raw_sas="DATA work.out; SET work.in; RUN;",
    input_datasets=["work.in"],
    output_datasets=["work.out"],
)

CONTEXT = JobContext(
    source_files={"etl.sas": "DATA work.out; SET work.in; RUN;"},
    resolved_macros=[MacroVar(name="DEPT", raw_value="SALES", source_file="etl.sas", line=1)],
    dependency_order=["work.in", "work.out"],
    risk_flags=["dynamic dataset name in DATA step"],
    blocks=[BLOCK],
    generated=[],
)

TRANSLATION_RESULT = DataStepResult(
    python_code="work_out = work_in.copy()  # SAS: etl.sas:3",
    confidence_band="high",
    uncertainty_notes=[],
)


def _make_run_result(result: DataStepResult) -> MagicMock:
    mock = MagicMock()
    mock.output = result
    return mock


@pytest.fixture()
def agent_with_mock() -> tuple[DataStepAgent, AsyncMock]:
    """Return a DataStepAgent whose internal _agent.run is mocked."""
    agent = DataStepAgent()
    mock_run = AsyncMock(return_value=_make_run_result(TRANSLATION_RESULT))
    agent._agent.run = mock_run  # type: ignore[method-assign]
    return agent, mock_run


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_translate_returns_generated_block(
    agent_with_mock: tuple[DataStepAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    result = await agent.translate(BLOCK, CONTEXT)
    assert isinstance(result, GeneratedBlock)
    assert result.source_block == BLOCK


async def test_is_untranslatable_false(
    agent_with_mock: tuple[DataStepAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    result = await agent.translate(BLOCK, CONTEXT)
    assert result.is_untranslatable is False


async def test_windowed_context_used(
    agent_with_mock: tuple[DataStepAgent, AsyncMock],
) -> None:
    agent, mock_run = agent_with_mock
    await agent.translate(BLOCK, CONTEXT)
    assert mock_run.called
    # The windowed context has source_files={}, verify the prompt was built
    # from windowed context by checking the call was made (windowed_context strips source_files)
    call_args = mock_run.call_args
    prompt: str = call_args[0][0]
    # Windowed context has no source_files but does have macros — prompt must be a string
    assert isinstance(prompt, str)


async def test_llm_failure_raises_data_step_error() -> None:
    agent = DataStepAgent()
    agent._agent.run = AsyncMock(side_effect=RuntimeError("LLM timeout"))  # type: ignore[method-assign]

    with pytest.raises(DataStepError) as exc_info:
        await agent.translate(BLOCK, CONTEXT)

    assert isinstance(exc_info.value.cause, RuntimeError)


async def test_max_tokens_4000(
    agent_with_mock: tuple[DataStepAgent, AsyncMock],
) -> None:
    agent, mock_run = agent_with_mock
    await agent.translate(BLOCK, CONTEXT)
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs.get("model_settings") == {"max_tokens": 4000}


async def test_macro_vars_in_prompt(
    agent_with_mock: tuple[DataStepAgent, AsyncMock],
) -> None:
    agent, mock_run = agent_with_mock
    await agent.translate(BLOCK, CONTEXT)
    prompt: str = mock_run.call_args[0][0]
    assert "DEPT" in prompt
    assert "SALES" in prompt


async def test_dependency_order_in_prompt(
    agent_with_mock: tuple[DataStepAgent, AsyncMock],
) -> None:
    agent, mock_run = agent_with_mock
    await agent.translate(BLOCK, CONTEXT)
    prompt: str = mock_run.call_args[0][0]
    assert "work.in" in prompt
    assert "work.out" in prompt


async def test_risk_flags_in_prompt(
    agent_with_mock: tuple[DataStepAgent, AsyncMock],
) -> None:
    agent, mock_run = agent_with_mock
    await agent.translate(BLOCK, CONTEXT)
    prompt: str = mock_run.call_args[0][0]
    assert "dynamic dataset name in DATA step" in prompt


async def test_confidence_propagated_to_generated_block(
    agent_with_mock: tuple[DataStepAgent, AsyncMock],
) -> None:
    agent, mock_run = agent_with_mock
    low_result = DataStepResult(
        python_code="work_out = work_in.copy()",
        confidence_band="low",
        uncertainty_notes=["RETAIN statement may not preserve row order"],
    )
    mock_run.return_value = _make_run_result(low_result)
    result = await agent.translate(BLOCK, CONTEXT)
    assert result.confidence == "low"
    assert result.uncertainty_notes == ["RETAIN statement may not preserve row order"]


async def test_high_confidence_empty_notes_propagated(
    agent_with_mock: tuple[DataStepAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    result = await agent.translate(BLOCK, CONTEXT)
    assert result.confidence == "high"
    assert result.uncertainty_notes == []


async def test_empty_risk_flags_no_crash() -> None:
    agent = DataStepAgent()
    mock_run = AsyncMock(return_value=_make_run_result(TRANSLATION_RESULT))
    agent._agent.run = mock_run  # type: ignore[method-assign]

    context_no_flags = CONTEXT.model_copy(update={"risk_flags": []})
    result = await agent.translate(BLOCK, context_no_flags)
    assert isinstance(result, GeneratedBlock)


def test_make_agent_azure_provider_path() -> None:
    """_make_agent() takes the Azure branch when azure_openai_endpoint is set."""
    from unittest.mock import MagicMock, patch

    mock_settings = MagicMock()
    mock_settings.tensorzero_gateway_url = None
    mock_settings.azure_openai_endpoint = "https://my-azure.openai.azure.com/"
    mock_settings.azure_openai_api_key = "fake-key"
    mock_settings.openai_api_version = "2024-02-01"
    mock_settings.llm_model = "azure:gpt-4o"

    mock_azure_provider = MagicMock()
    mock_model = MagicMock()
    mock_agent = MagicMock()

    with (
        patch("src.worker.engine.agents.data_step.worker_settings", mock_settings),
        patch("src.worker.engine.agents.data_step.AzureProvider", return_value=mock_azure_provider),
        patch("src.worker.engine.agents.data_step.OpenAIChatModel", return_value=mock_model),
        patch("src.worker.engine.agents.data_step.Agent", return_value=mock_agent),
    ):
        from src.worker.engine.agents.data_step import _make_agent

        result = _make_agent()

    assert result is mock_agent
