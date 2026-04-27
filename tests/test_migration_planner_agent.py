"""Unit tests for MigrationPlannerAgent."""

# SAS: tests/test_migration_planner_agent.py:1

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.worker.engine.agents.migration_planner import (
    MigrationPlannerAgent,
    MigrationPlannerError,
    PlannerResult,
)
from src.worker.engine.models import (
    BlockRisk,
    BlockType,
    JobContext,
    MacroVar,
    SASBlock,
    TranslationStrategy,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_MACRO_VARS: list[MacroVar] = [
    MacroVar(name="DEPT", raw_value="SALES", source_file="etl.sas", line=1)
]

_BLOCKS: list[SASBlock] = [
    SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file="etl.sas",
        start_line=2,
        end_line=5,
        raw_sas="DATA work.out; SET work.in; RUN;",
        input_datasets=["work.in"],
        output_datasets=["work.out"],
    ),
    SASBlock(
        block_type=BlockType.PROC_SQL,
        source_file="etl.sas",
        start_line=7,
        end_line=12,
        raw_sas="PROC SQL; SELECT * FROM work.out; QUIT;",
        input_datasets=["work.out"],
        output_datasets=[],
    ),
]

_CONTEXT = JobContext(
    source_files={
        "etl.sas": "DATA work.out; SET work.in; RUN;\nPROC SQL; SELECT * FROM work.out; QUIT;"
    },
    resolved_macros=_MACRO_VARS,
    dependency_order=["work.in", "work.out"],
    risk_flags=[],
    blocks=_BLOCKS,
    generated=[],
    reconciliation=None,
)

_PLANNER_RESULT = PlannerResult(
    summary="This codebase extracts sales data and produces a summary report.",
    overall_risk="medium",
    block_plans=[
        {
            "block_id": "etl.sas:2",
            "source_file": "etl.sas",
            "start_line": 2,
            "block_type": "DATA_STEP",
            "strategy": "translated",
            "risk": "low",
            "rationale": "Simple SET/filter step with no complex constructs.",
            "estimated_effort": "low",
        },
        {
            "block_id": "etl.sas:7",
            "source_file": "etl.sas",
            "start_line": 7,
            "block_type": "PROC_SQL",
            "strategy": "translated",
            "risk": "medium",
            "rationale": "Straightforward SELECT but references cross-file dataset.",
            "estimated_effort": "medium",
        },
    ],
    recommended_review_blocks=["etl.sas:7"],
    cross_file_dependencies=["work.out flows from etl.sas DATA step into PROC SQL"],
)


def _make_run_result(planner: PlannerResult) -> MagicMock:
    mock = MagicMock()
    mock.output = planner
    return mock


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.fixture()
def agent_with_mock() -> tuple[MigrationPlannerAgent, AsyncMock]:
    """Return a MigrationPlannerAgent whose internal _agent.run is mocked."""
    agent = MigrationPlannerAgent()
    mock_run = AsyncMock(return_value=_make_run_result(_PLANNER_RESULT))
    agent._agent.run = mock_run  # type: ignore[method-assign]
    return agent, mock_run


async def test_plan_returns_migration_plan_summary(
    agent_with_mock: tuple[MigrationPlannerAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    plan = await agent.plan(_CONTEXT)
    assert "sales" in plan.summary.lower()


async def test_plan_overall_risk_parsed(
    agent_with_mock: tuple[MigrationPlannerAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    plan = await agent.plan(_CONTEXT)
    assert plan.overall_risk == BlockRisk.MEDIUM


async def test_plan_block_plans_count(
    agent_with_mock: tuple[MigrationPlannerAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    plan = await agent.plan(_CONTEXT)
    assert len(plan.block_plans) == 2


async def test_plan_block_strategy_and_risk(
    agent_with_mock: tuple[MigrationPlannerAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    plan = await agent.plan(_CONTEXT)
    first = plan.block_plans[0]
    assert first.block_id == "etl.sas:2"
    assert first.strategy == TranslationStrategy.TRANSLATED
    assert first.risk == BlockRisk.LOW


async def test_plan_recommended_review_blocks(
    agent_with_mock: tuple[MigrationPlannerAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    plan = await agent.plan(_CONTEXT)
    assert "etl.sas:7" in plan.recommended_review_blocks


async def test_plan_cross_file_dependencies(
    agent_with_mock: tuple[MigrationPlannerAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    plan = await agent.plan(_CONTEXT)
    assert len(plan.cross_file_dependencies) == 1
    assert "work.out" in plan.cross_file_dependencies[0]


async def test_plan_raises_migration_planner_error_on_llm_failure() -> None:
    agent = MigrationPlannerAgent()
    agent._agent.run = AsyncMock(side_effect=RuntimeError("LLM timeout"))  # type: ignore[method-assign]

    with pytest.raises(MigrationPlannerError) as exc_info:
        await agent.plan(_CONTEXT)

    assert "MigrationPlannerAgent failed" in str(exc_info.value)
    assert isinstance(exc_info.value.cause, RuntimeError)


async def test_plan_passes_max_tokens_6000(
    agent_with_mock: tuple[MigrationPlannerAgent, AsyncMock],
) -> None:
    agent, mock_run = agent_with_mock
    await agent.plan(_CONTEXT)
    _, kwargs = mock_run.call_args
    assert kwargs.get("model_settings", {}).get("max_tokens") == 6000


# ── _build_prompt with non-empty optional fields (lines 169-179) ─────────────


def test_build_prompt_includes_resolved_macros() -> None:
    """_build_prompt includes resolved macros section when present (lines 241-247)."""
    from src.worker.engine.agents.migration_planner import _build_prompt

    prompt = _build_prompt(_CONTEXT)

    assert "DEPT" in prompt
    assert "SALES" in prompt
    assert "etl.sas" in prompt


def test_build_prompt_includes_log_contents() -> None:
    """_build_prompt includes SAS log section when log_contents is non-empty (lines 265-274)."""
    from src.worker.engine.agents.migration_planner import _build_prompt

    context_with_logs = _CONTEXT.model_copy(
        update={
            "log_contents": {
                "etl.log": "NOTE: 200 observations read.\nNOTE: Dataset WORK.OUT has 200 obs."
            }
        }
    )
    prompt = _build_prompt(context_with_logs)

    assert "SAS execution logs" in prompt
    assert "NOTE: 200 observations read" in prompt
    assert "etl.log" in prompt


def test_build_prompt_no_macros_emits_none_placeholder() -> None:
    """_build_prompt emits (none) for macros when resolved_macros is empty (line 247)."""
    from src.worker.engine.agents.migration_planner import _build_prompt

    context_no_macros = _CONTEXT.model_copy(update={"resolved_macros": []})
    prompt = _build_prompt(context_no_macros)

    assert "(none)" in prompt


# ── _make_agent TensorZero branch (line 247) and Azure branch (lines 266-274) ─


def test_migration_planner_make_agent_tensorzero_branch() -> None:
    """_make_agent uses TensorZero provider when tensorzero_gateway_url is set (line 247)."""
    from unittest.mock import MagicMock, patch

    mock_provider = MagicMock()
    mock_model = MagicMock()
    mock_agent = MagicMock()

    with (
        patch("src.worker.engine.agents.migration_planner.worker_settings") as mock_settings,
        patch(
            "src.worker.engine.agents.migration_planner.OpenAIProvider",
            return_value=mock_provider,
        ) as mock_oi,
        patch(
            "src.worker.engine.agents.migration_planner.OpenAIChatModel",
            return_value=mock_model,
        ) as mock_oai,
        patch("src.worker.engine.agents.migration_planner.Agent", return_value=mock_agent),
    ):
        mock_settings.tensorzero_gateway_url = "http://tensorzero:3000"
        mock_settings.azure_openai_endpoint = None
        mock_settings.llm_model = "openai:gpt-4o"

        from src.worker.engine.agents.migration_planner import _make_agent

        result = _make_agent()

    mock_oi.assert_called_once_with(
        base_url="http://tensorzero:3000",
        api_key="tensorzero",
    )
    mock_oai.assert_called_once_with(
        model_name="tensorzero::model_name::gpt-4o", provider=mock_provider
    )
    assert result is mock_agent


def test_migration_planner_make_agent_azure_branch() -> None:
    """_make_agent uses AzureProvider when azure_openai_endpoint is set (lines 266-274)."""
    from unittest.mock import MagicMock, patch

    mock_provider = MagicMock()
    mock_model = MagicMock()
    mock_agent = MagicMock()

    with (
        patch("src.worker.engine.agents.migration_planner.worker_settings") as mock_settings,
        patch(
            "src.worker.engine.agents.migration_planner.AzureProvider",
            return_value=mock_provider,
        ) as mock_az,
        patch(
            "src.worker.engine.agents.migration_planner.OpenAIChatModel",
            return_value=mock_model,
        ) as mock_oai,
        patch("src.worker.engine.agents.migration_planner.Agent", return_value=mock_agent),
    ):
        mock_settings.tensorzero_gateway_url = None
        mock_settings.azure_openai_endpoint = "https://az.openai.azure.com/"
        mock_settings.azure_openai_api_key = "az-key"
        mock_settings.openai_api_version = "2024-06-01"
        mock_settings.llm_model = "openai:gpt-4o"

        from src.worker.engine.agents.migration_planner import _make_agent

        result = _make_agent()

    mock_az.assert_called_once_with(
        azure_endpoint="https://az.openai.azure.com/",
        api_key="az-key",
        api_version="2024-06-01",
    )
    mock_oai.assert_called_once_with(model_name="gpt-4o", provider=mock_provider)
    assert result is mock_agent
