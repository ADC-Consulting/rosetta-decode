"""Unit tests for GenericProcAgent."""

# SAS: tests/test_generic_proc_agent.py:1

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.worker.engine.agents.generic_proc import GenericProcAgent, GenericProcResult
from src.worker.engine.models import BlockType, GeneratedBlock, JobContext, SASBlock

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_block(
    block_type: BlockType = BlockType.PROC_IML,
    raw_sas: str = "PROC IML; x = {1,2,3}; RUN;",
    source_file: str = "test.sas",
    start_line: int = 1,
) -> SASBlock:
    return SASBlock(
        block_type=block_type,
        source_file=source_file,
        start_line=start_line,
        end_line=start_line + 3,
        raw_sas=raw_sas,
        input_datasets=[],
        output_datasets=[],
    )


def _make_context() -> JobContext:
    return JobContext(
        source_files={"test.sas": "PROC IML; x = {1,2,3}; RUN;"},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        blocks=[],
        generated=[],
        reconciliation=None,
    )


def _make_run_result(result: GenericProcResult) -> MagicMock:
    mock = MagicMock()
    mock.output = result
    return mock


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.fixture()
def agent_with_mock() -> tuple[GenericProcAgent, AsyncMock]:
    agent = GenericProcAgent()
    mock_run = AsyncMock(
        return_value=_make_run_result(
            GenericProcResult(
                python_code="import numpy as np\nx = np.array([1, 2, 3])  # SAS: test.sas:1",
                strategy_used="translate",
                confidence_score=0.75,
                confidence_band="medium",
                uncertainty_notes=["Column-major memory order differs from NumPy default."],
                assumptions=["IML matrix literal maps to 1-D numpy array."],
                detected_features=[],
            )
        )
    )
    agent._agent.run = mock_run  # type: ignore[method-assign]
    return agent, mock_run


async def test_proc_iml_returns_generated_block(
    agent_with_mock: tuple[GenericProcAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    block = _make_block(BlockType.PROC_IML)
    result = await agent.translate(block, _make_context())
    assert isinstance(result, GeneratedBlock)
    assert result.python_code != ""
    assert result.is_untranslatable is False


async def test_proc_iml_confidence_propagated(
    agent_with_mock: tuple[GenericProcAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    block = _make_block(BlockType.PROC_IML)
    result = await agent.translate(block, _make_context())
    assert result.confidence_score == pytest.approx(0.75)
    assert result.confidence_band == "medium"


async def test_proc_iml_uncertainty_notes(
    agent_with_mock: tuple[GenericProcAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    block = _make_block(BlockType.PROC_IML)
    result = await agent.translate(block, _make_context())
    assert len(result.uncertainty_notes) == 1
    assert "Column-major" in result.uncertainty_notes[0]


async def test_proc_iml_assumptions_propagated(
    agent_with_mock: tuple[GenericProcAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    block = _make_block(BlockType.PROC_IML)
    result = await agent.translate(block, _make_context())
    assert len(result.assumptions) == 1
    assert "numpy" in result.assumptions[0].lower()


async def test_proc_fcmp_translate_strategy(
    agent_with_mock: tuple[GenericProcAgent, AsyncMock],
) -> None:
    """PROC FCMP should default to translate strategy."""
    agent, mock_run = agent_with_mock
    mock_run.return_value = _make_run_result(
        GenericProcResult(
            python_code=(
                "def logit(x):\n    import numpy as np\n"
                "    return np.log(x / (1 - x))  # SAS: test.sas:1"
            ),
            strategy_used="translate",
            confidence_score=0.9,
            confidence_band="high",
            uncertainty_notes=[],
            assumptions=[],
            detected_features=[],
        )
    )
    block = _make_block(
        BlockType.PROC_FCMP,
        raw_sas="PROC FCMP; FUNCTION logit(x); RETURN(LOG(x/(1-x))); ENDFUNC; RUN;",
    )
    result = await agent.translate(block, _make_context())
    assert result.strategy_used == "translate"
    assert "def logit" in result.python_code


async def test_proc_optmodel_detected_features_allows_manual(
    agent_with_mock: tuple[GenericProcAgent, AsyncMock],
) -> None:
    """PROC OPTMODEL with non-empty detected_features may return manual strategy."""
    agent, mock_run = agent_with_mock
    mock_run.return_value = _make_run_result(
        GenericProcResult(
            python_code=(
                "# TODO: PROC OPTMODEL with custom solver requires manual port\n# SAS: test.sas:1"
            ),
            strategy_used="manual",
            confidence_score=0.3,
            confidence_band="low",
            uncertainty_notes=["PROC OPTMODEL custom solver not directly mappable."],
            assumptions=[],
            detected_features=["custom_solver"],
        )
    )
    block = _make_block(
        BlockType.PROC_OPTMODEL,
        raw_sas="PROC OPTMODEL; /* complex */ RUN;",
    )
    result = await agent.translate(block, _make_context())
    assert result.strategy_used == "manual"
    assert result.confidence_band == "low"


async def test_proc_unknown_returns_best_effort_code(
    agent_with_mock: tuple[GenericProcAgent, AsyncMock],
) -> None:
    """PROC_UNKNOWN must always produce real code, not an empty string."""
    agent, mock_run = agent_with_mock
    mock_run.return_value = _make_run_result(
        GenericProcResult(
            python_code="# Best-effort translation of unknown PROC\n# SAS: test.sas:1\npass",
            strategy_used="translate_with_review",
            confidence_score=0.5,
            confidence_band="low",
            uncertainty_notes=["PROC MIXED is not a known SAS procedure in our catalog."],
            assumptions=[],
            detected_features=[],
        )
    )
    block = _make_block(BlockType.PROC_UNKNOWN, raw_sas="PROC MIXED; MODEL y = x; RUN;")
    result = await agent.translate(block, _make_context())
    assert result.python_code.strip() != ""
    assert result.is_untranslatable is False


# ── GenericProcError with cause (lines 57-58) ────────────────────────────────


def test_generic_proc_error_stores_cause() -> None:
    """GenericProcError.__init__ stores the cause exception (lines 57-58)."""
    from src.worker.engine.agents.generic_proc import GenericProcError

    underlying = ValueError("underlying failure")
    err = GenericProcError("wrapper message", cause=underlying)

    assert str(err) == "wrapper message"
    assert err.cause is underlying
    assert isinstance(err.cause, ValueError)


# ── _build_prompt branches (lines 261-288) ───────────────────────────────────


def test_build_prompt_with_all_context_fields() -> None:
    """_build_prompt includes macros, deps, risk_flags and log_contents when populated."""
    from src.worker.engine.agents.generic_proc import _build_prompt
    from src.worker.engine.models import MacroVar

    block = SASBlock(
        block_type=BlockType.PROC_MEANS,
        source_file="test.sas",
        start_line=1,
        end_line=4,
        raw_sas="PROC MEANS DATA=work; VAR salary; RUN;",
        input_datasets=["work.salary_data"],
        output_datasets=["work.out"],
    )

    context = JobContext(
        source_files={"test.sas": "PROC MEANS DATA=work; VAR salary; RUN;"},
        resolved_macros=[MacroVar(name="DEPT", raw_value="SALES", source_file="test.sas", line=1)],
        dependency_order=["work.salary_data", "work.out"],
        risk_flags=["BY-group processing", "RETAIN in loop"],
        blocks=[block],
        generated=[],
        log_contents={"test.log": "NOTE: 100 observations read.\nWARNING: numeric overflow"},
    )
    windowed = context.windowed_context(block)
    prompt = _build_prompt(block, windowed, context.blocks)

    assert "DEPT" in prompt
    assert "SALES" in prompt
    assert "work.out" in prompt
    assert "BY-group processing" in prompt
    assert "NOTE: 100 observations read" in prompt


def test_build_prompt_empty_context() -> None:
    """_build_prompt emits (none) placeholders when all context lists are empty."""
    from src.worker.engine.agents.generic_proc import _build_prompt

    block = _make_block(BlockType.PROC_FREQ)
    context = _make_context()
    windowed = context.windowed_context(block)
    prompt = _build_prompt(block, windowed, [])

    assert "(none)" in prompt


# ── _make_agent TensorZero and Azure branches (lines 324-334) ────────────────


def test_generic_proc_make_agent_tensorzero_branch() -> None:
    """_make_agent routes through OpenAIProvider when tensorzero_gateway_url is set."""
    from unittest.mock import patch

    mock_provider = MagicMock()
    mock_model = MagicMock()
    mock_agent = MagicMock()

    with (
        patch("src.worker.engine.agents.generic_proc.worker_settings") as mock_settings,
        patch(
            "src.worker.engine.agents.generic_proc.OpenAIProvider", return_value=mock_provider
        ) as mock_oi,
        patch(
            "src.worker.engine.agents.generic_proc.OpenAIChatModel", return_value=mock_model
        ) as mock_oai,
        patch("src.worker.engine.agents.generic_proc.Agent", return_value=mock_agent),
    ):
        mock_settings.tensorzero_gateway_url = "http://tensorzero:3000"
        mock_settings.azure_openai_endpoint = None
        mock_settings.llm_model = "openai:gpt-4o"

        from src.worker.engine.agents.generic_proc import _make_agent

        result = _make_agent()

    mock_oi.assert_called_once_with(
        base_url="http://tensorzero:3000",
        api_key="tensorzero",
    )
    mock_oai.assert_called_once_with(
        model_name="tensorzero::model_name::gpt-4o", provider=mock_provider
    )
    assert result is mock_agent


def test_generic_proc_make_agent_azure_branch() -> None:
    """_make_agent routes through AzureProvider when azure_openai_endpoint is set."""
    from unittest.mock import patch

    mock_provider = MagicMock()
    mock_model = MagicMock()
    mock_agent = MagicMock()

    with (
        patch("src.worker.engine.agents.generic_proc.worker_settings") as mock_settings,
        patch(
            "src.worker.engine.agents.generic_proc.AzureProvider", return_value=mock_provider
        ) as mock_az,
        patch(
            "src.worker.engine.agents.generic_proc.OpenAIChatModel", return_value=mock_model
        ) as mock_oai,
        patch("src.worker.engine.agents.generic_proc.Agent", return_value=mock_agent),
    ):
        mock_settings.tensorzero_gateway_url = None
        mock_settings.azure_openai_endpoint = "https://az.openai.azure.com/"
        mock_settings.azure_openai_api_key = "az-key"
        mock_settings.openai_api_version = "2024-06-01"
        mock_settings.llm_model = "openai:gpt-4o"

        from src.worker.engine.agents.generic_proc import _make_agent

        result = _make_agent()

    mock_az.assert_called_once_with(
        azure_endpoint="https://az.openai.azure.com/",
        api_key="az-key",
        api_version="2024-06-01",
    )
    mock_oai.assert_called_once_with(model_name="gpt-4o", provider=mock_provider)
    assert result is mock_agent


# ── Exception path in GenericProcAgent.translate() (lines 379-381) ──────────


async def test_translate_raises_generic_proc_error_on_llm_failure() -> None:
    """translate() wraps LLM exceptions in GenericProcError (lines 379-381)."""
    from src.worker.engine.agents.generic_proc import GenericProcError

    agent = GenericProcAgent()
    agent._agent.run = AsyncMock(side_effect=RuntimeError("LLM call failed"))  # type: ignore[method-assign]

    block = _make_block(BlockType.PROC_MEANS)
    with pytest.raises(GenericProcError) as exc_info:
        await agent.translate(block, _make_context())

    assert "GenericProcAgent failed" in str(exc_info.value)
    assert isinstance(exc_info.value.cause, RuntimeError)
