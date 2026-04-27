"""Unit tests for FailureInterpreterAgent."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.worker.engine.agents.failure_interpreter import (
    FailureInterpretation,
    FailureInterpreterAgent,
    FailureInterpreterError,
)
from src.worker.engine.models import JobContext, MacroVar

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_context() -> JobContext:
    return JobContext(
        source_files={"etl.sas": "DATA out; SET in; RUN;"},
        resolved_macros=[MacroVar(name="X", raw_value="1", source_file="etl.sas", line=1)],
        dependency_order=["in", "out"],
        risk_flags=["dynamic dataset name"],
        blocks=[],
        generated=[],
    )


def _make_run_result(interp: FailureInterpretation) -> MagicMock:
    mock = MagicMock()
    mock.output = interp
    return mock


SAMPLE_DIFF = """\
- 1,SALES,100
+ 1,SALES,99
"""

SAMPLE_CODE = """\
# SAS: etl.sas:7
out = inp.copy()
out['val'] = out['val'] * 1.0
"""


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_interpret_returns_correct_tuple_shape() -> None:
    """interpret() must return (retry_hint: str, affected_block_id: str)."""
    agent = FailureInterpreterAgent()
    interp = FailureInterpretation(
        retry_hint="Use integer division for salary calculation.",
        affected_block_id="etl.sas:7",
    )
    agent._agent.run = AsyncMock(  # type: ignore[method-assign]
        return_value=_make_run_result(interp)
    )

    context = _make_context()
    hint, block_id = await agent.interpret(SAMPLE_DIFF, SAMPLE_CODE, context)

    assert hint == "Use integer division for salary calculation."
    assert block_id == "etl.sas:7"


@pytest.mark.asyncio
async def test_interpret_passes_diff_and_code_to_agent() -> None:
    """The prompt sent to the agent must contain both the diff and the generated code."""
    agent = FailureInterpreterAgent()
    interp = FailureInterpretation(retry_hint="fix it", affected_block_id="etl.sas:1")
    run_mock = AsyncMock(return_value=_make_run_result(interp))
    agent._agent.run = run_mock  # type: ignore[method-assign]

    await agent.interpret(SAMPLE_DIFF, SAMPLE_CODE, _make_context())

    call_prompt: str = run_mock.call_args[0][0]
    assert "1,SALES,100" in call_prompt
    assert "# SAS: etl.sas:7" in call_prompt


@pytest.mark.asyncio
async def test_interpret_tagged_correctly() -> None:
    """System prompt must contain the agent tag for TensorZero routing."""
    # The system prompt is embedded in _SYSTEM_PROMPT constant
    from src.worker.engine.agents.failure_interpreter import _SYSTEM_PROMPT

    assert "# agent: FailureInterpreterAgent" in _SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_interpret_raises_failure_interpreter_error_on_llm_failure() -> None:
    """interpret() must raise FailureInterpreterError when the LLM call throws."""
    agent = FailureInterpreterAgent()
    agent._agent.run = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("network error")
    )

    with pytest.raises(FailureInterpreterError) as exc_info:
        await agent.interpret(SAMPLE_DIFF, SAMPLE_CODE, _make_context())

    assert isinstance(exc_info.value.cause, RuntimeError)


@pytest.mark.asyncio
async def test_failure_interpretation_model_shape() -> None:
    """FailureInterpretation must have retry_hint and affected_block_id fields."""
    fi = FailureInterpretation(retry_hint="hint", affected_block_id="a.sas:1")
    assert fi.retry_hint == "hint"
    assert fi.affected_block_id == "a.sas:1"


def test_failure_interpreter_error_stores_cause() -> None:
    """FailureInterpreterError must expose the cause attribute."""
    cause = ValueError("root")
    err = FailureInterpreterError("failed", cause=cause)
    assert err.cause is cause
    assert "failed" in str(err)


def test_build_prompt_contains_diff_code_and_flags() -> None:
    """_build_prompt() must include diff, generated code, and risk flags."""
    from src.worker.engine.agents.failure_interpreter import _build_prompt

    context = _make_context()
    prompt = _build_prompt(SAMPLE_DIFF, SAMPLE_CODE, context)

    assert "1,SALES,100" in prompt
    assert "# SAS: etl.sas:7" in prompt
    assert "dynamic dataset name" in prompt


def test_failure_interpreter_make_agent_tensorzero_path() -> None:
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
        patch("src.worker.engine.agents.failure_interpreter.worker_settings", mock_settings),
        patch(
            "src.worker.engine.agents.failure_interpreter.OpenAIProvider",
            return_value=mock_tz_provider,
        ),
        patch(
            "src.worker.engine.agents.failure_interpreter.OpenAIChatModel",
            return_value=mock_model,
        ) as mock_oai_model,
        patch("src.worker.engine.agents.failure_interpreter.Agent", return_value=mock_agent),
    ):
        from src.worker.engine.agents.failure_interpreter import _make_agent

        result = _make_agent()

    call_kwargs = mock_oai_model.call_args
    first_arg = call_kwargs.args[0] if call_kwargs.args else ""
    model_name_arg = call_kwargs.kwargs.get("model_name", first_arg)
    assert "tensorzero::" in model_name_arg
    assert result is mock_agent


def test_failure_interpreter_make_agent_azure_path() -> None:
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
        patch("src.worker.engine.agents.failure_interpreter.worker_settings", mock_settings),
        patch(
            "src.worker.engine.agents.failure_interpreter.AzureProvider",
            return_value=mock_azure_provider,
        ) as mock_az,
        patch(
            "src.worker.engine.agents.failure_interpreter.OpenAIChatModel",
            return_value=mock_model,
        ),
        patch("src.worker.engine.agents.failure_interpreter.Agent", return_value=mock_agent),
    ):
        from src.worker.engine.agents.failure_interpreter import _make_agent

        result = _make_agent()

    mock_az.assert_called_once()
    assert result is mock_agent
