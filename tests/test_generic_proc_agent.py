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
