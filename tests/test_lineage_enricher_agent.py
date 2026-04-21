"""Unit tests for LineageEnricherAgent."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.worker.engine.agents.lineage_enricher import (
    LineageEnricherAgent,
    LineageEnricherError,
    LineageEnrichmentResult,
)
from src.worker.engine.models import (
    BlockType,
    ColumnFlow,
    EnrichedLineage,
    FileNode,
    JobContext,
    MacroUsage,
    MacroVar,
    PipelineStep,
    SASBlock,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_MACRO_VAR = MacroVar(name="DEPT", raw_value="SALES", source_file="etl.sas", line=1)

_BLOCK = SASBlock(
    block_type=BlockType.DATA_STEP,
    source_file="etl.sas",
    start_line=2,
    end_line=4,
    raw_sas="DATA work.out; SET work.in; KEEP id name; RUN;",
    input_datasets=["work.in"],
    output_datasets=["work.out"],
)

_JOB_CONTEXT = JobContext(
    source_files={"etl.sas": "%LET dept = SALES;\nDATA work.out; SET work.in; KEEP id name; RUN;"},
    resolved_macros=[_MACRO_VAR],
    dependency_order=["work.in", "work.out"],
    risk_flags=[],
    blocks=[_BLOCK],
    generated=[],
    reconciliation=None,
)

_ENRICHMENT_RESULT = LineageEnrichmentResult(
    column_flows=[
        ColumnFlow(
            column="id",
            source_dataset="work.in",
            target_dataset="work.out",
            via_block_id="etl.sas:2",
            transformation=None,
        ),
        ColumnFlow(
            column="name",
            source_dataset="work.in",
            target_dataset="work.out",
            via_block_id="etl.sas:2",
            transformation=None,
        ),
    ],
    macro_usages=[
        MacroUsage(
            macro_name="DEPT",
            macro_value="SALES",
            used_in_block_id="etl.sas:2",
        )
    ],
    cross_file_edges=[],
    dataset_summaries={
        "work.in": "Source dataset containing id and name columns.",
        "work.out": "Output dataset with id and name kept from work.in.",
    },
    file_nodes=[],
    file_edges=[],
    pipeline_steps=[],
    block_status=[],
    log_links=[],
)


def _make_run_result(enrichment: LineageEnrichmentResult) -> MagicMock:
    mock = MagicMock()
    mock.output = enrichment
    return mock


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.fixture()
def agent_with_mock() -> tuple[LineageEnricherAgent, AsyncMock]:
    """Return a LineageEnricherAgent whose internal _agent.run is mocked."""
    agent = LineageEnricherAgent()
    mock_run = AsyncMock(return_value=_make_run_result(_ENRICHMENT_RESULT))
    agent._agent.run = mock_run  # type: ignore[method-assign]
    return agent, mock_run


async def test_enrich_returns_enriched_lineage_type(
    agent_with_mock: tuple[LineageEnricherAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    result = await agent.enrich(_JOB_CONTEXT)
    assert isinstance(result, EnrichedLineage)


async def test_enrich_populates_column_flows(
    agent_with_mock: tuple[LineageEnricherAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    result = await agent.enrich(_JOB_CONTEXT)
    assert len(result.column_flows) == 2
    assert result.column_flows[0].column == "id"
    assert result.column_flows[0].source_dataset == "work.in"
    assert result.column_flows[0].target_dataset == "work.out"
    assert result.column_flows[0].via_block_id == "etl.sas:2"
    assert result.column_flows[0].transformation is None


async def test_enrich_populates_macro_usages(
    agent_with_mock: tuple[LineageEnricherAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    result = await agent.enrich(_JOB_CONTEXT)
    assert len(result.macro_usages) == 1
    assert result.macro_usages[0].macro_name == "DEPT"
    assert result.macro_usages[0].macro_value == "SALES"
    assert result.macro_usages[0].used_in_block_id == "etl.sas:2"


async def test_enrich_populates_cross_file_edges(
    agent_with_mock: tuple[LineageEnricherAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    result = await agent.enrich(_JOB_CONTEXT)
    assert result.cross_file_edges == []


async def test_enrich_populates_dataset_summaries(
    agent_with_mock: tuple[LineageEnricherAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    result = await agent.enrich(_JOB_CONTEXT)
    assert "work.in" in result.dataset_summaries
    assert "work.out" in result.dataset_summaries


async def test_enrich_passes_max_tokens_to_llm(
    agent_with_mock: tuple[LineageEnricherAgent, AsyncMock],
) -> None:
    agent, mock_run = agent_with_mock
    await agent.enrich(_JOB_CONTEXT)
    _, kwargs = mock_run.call_args
    assert kwargs.get("model_settings", {}).get("max_tokens") == 16000


async def test_enrich_raises_lineage_enricher_error_on_llm_failure() -> None:
    agent = LineageEnricherAgent()
    agent._agent.run = AsyncMock(side_effect=RuntimeError("LLM timeout"))  # type: ignore[method-assign]

    with pytest.raises(LineageEnricherError) as exc_info:
        await agent.enrich(_JOB_CONTEXT)

    assert "LineageEnricherAgent failed" in str(exc_info.value)
    assert isinstance(exc_info.value.cause, RuntimeError)


async def test_enrich_populates_file_nodes(
    agent_with_mock: tuple[LineageEnricherAgent, AsyncMock],
) -> None:
    agent, mock_run = agent_with_mock
    populated = LineageEnrichmentResult(
        column_flows=[],
        macro_usages=[],
        cross_file_edges=[],
        dataset_summaries={},
        file_nodes=[
            FileNode(
                filename="etl.sas",
                file_type="PROGRAM",
                blocks=["etl.sas:2"],
                status="OK",
                status_reason=None,
            )
        ],
        file_edges=[],
        pipeline_steps=[],
        block_status=[],
        log_links=[],
    )
    mock_run.return_value = _make_run_result(populated)
    result = await agent.enrich(_JOB_CONTEXT)
    assert len(result.file_nodes) == 1
    assert result.file_nodes[0].filename == "etl.sas"
    assert result.file_nodes[0].file_type == "PROGRAM"
    assert result.file_nodes[0].status == "OK"


async def test_enrich_populates_pipeline_steps(
    agent_with_mock: tuple[LineageEnricherAgent, AsyncMock],
) -> None:
    agent, mock_run = agent_with_mock
    populated = LineageEnrichmentResult(
        column_flows=[],
        macro_usages=[],
        cross_file_edges=[],
        dataset_summaries={},
        file_nodes=[],
        file_edges=[],
        pipeline_steps=[
            PipelineStep(
                step_id="step_1",
                name="Load and filter",
                description="Reads work.in and writes work.out.",
                files=["etl.sas"],
                blocks=["etl.sas:2"],
                inputs=["work.in"],
                outputs=["work.out"],
            )
        ],
        block_status=[],
        log_links=[],
    )
    mock_run.return_value = _make_run_result(populated)
    result = await agent.enrich(_JOB_CONTEXT)
    assert len(result.pipeline_steps) == 1
    assert result.pipeline_steps[0].step_id == "step_1"
    assert result.pipeline_steps[0].inputs == ["work.in"]
    assert result.pipeline_steps[0].outputs == ["work.out"]
