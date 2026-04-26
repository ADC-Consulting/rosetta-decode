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
