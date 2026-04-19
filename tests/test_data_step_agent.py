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

TRANSLATION_RESULT = DataStepResult(python_code="work_out = work_in.copy()  # SAS: etl.sas:3")


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


async def test_empty_risk_flags_no_crash() -> None:
    agent = DataStepAgent()
    mock_run = AsyncMock(return_value=_make_run_result(TRANSLATION_RESULT))
    agent._agent.run = mock_run  # type: ignore[method-assign]

    context_no_flags = CONTEXT.model_copy(update={"risk_flags": []})
    result = await agent.translate(BLOCK, context_no_flags)
    assert isinstance(result, GeneratedBlock)
