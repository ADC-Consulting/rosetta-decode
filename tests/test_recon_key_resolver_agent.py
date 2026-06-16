"""Unit tests for ReconKeyResolverAgent (F15 LLM join-key resolution)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from src.worker.engine.agents.recon_key_resolver import (
    KeyResolution,
    ReconKeyResolverAgent,
    ReconKeyResolverError,
    build_candidate_stats,
)


def _make_run_result(result: KeyResolution) -> MagicMock:
    mock = MagicMock()
    mock.output = result
    return mock


@pytest.fixture()
def agent_with_mock() -> tuple[ReconKeyResolverAgent, AsyncMock]:
    """Return a ReconKeyResolverAgent whose internal _agent.run is mocked."""
    agent = ReconKeyResolverAgent()
    resolution = KeyResolution(
        proposed_keys=["subjid", "aestdtc", "aeterm"],
        rationale="subject + date + event term is the AE business key",
        confidence_score=0.8,
    )
    mock_run = AsyncMock(return_value=_make_run_result(resolution))
    agent._agent.run = mock_run  # type: ignore[method-assign]
    return agent, mock_run


async def test_resolve_returns_lowercased_keys(
    agent_with_mock: tuple[ReconKeyResolverAgent, AsyncMock],
) -> None:
    agent, _ = agent_with_mock
    result = await agent.resolve(
        failure_detail="join_keys=['subjid','aestdtc']; 11 differing cell-group(s)",
        ref_schema=["subjid", "aestdtc", "aeterm"],
        actual_schema=["subjid", "aestdtc", "aeterm"],
        raw_sas="data ae; set sdtm.ae; run;",
        candidate_stats="subjid: ref_null=0.000",
    )
    assert result.proposed_keys == ["subjid", "aestdtc", "aeterm"]


async def test_prompt_carries_failure_schemas_sas_stats_and_feedback(
    agent_with_mock: tuple[ReconKeyResolverAgent, AsyncMock],
) -> None:
    agent, mock_run = agent_with_mock
    await agent.resolve(
        failure_detail="UNIQUE_FAILURE_DETAIL_TOKEN",
        ref_schema=["subjid", "REF_SCHEMA_COL"],
        actual_schema=["subjid", "ACTUAL_SCHEMA_COL"],
        raw_sas="RAW_SAS_TOKEN proc sort; run;",
        candidate_stats="CANDIDATE_STATS_TOKEN: ref_null=0.0",
        attempts_feedback="- tried ['subjid', 'aestdtc']: still diffs  <-- CLOSEST so far",
    )
    prompt: str = mock_run.call_args[0][0]
    assert "UNIQUE_FAILURE_DETAIL_TOKEN" in prompt
    assert "REF_SCHEMA_COL" in prompt
    assert "ACTUAL_SCHEMA_COL" in prompt
    assert "RAW_SAS_TOKEN" in prompt
    assert "CANDIDATE_STATS_TOKEN" in prompt
    assert "CLOSEST so far" in prompt


async def test_resolve_wraps_llm_failure() -> None:
    agent = ReconKeyResolverAgent()
    agent._agent.run = AsyncMock(side_effect=RuntimeError("LLM down"))  # type: ignore[method-assign]
    with pytest.raises(ReconKeyResolverError) as exc_info:
        await agent.resolve(
            failure_detail="x",
            ref_schema=["a"],
            actual_schema=["a"],
            raw_sas="data x; run;",
            candidate_stats="",
        )
    assert isinstance(exc_info.value.cause, RuntimeError)


def test_build_candidate_stats_reports_common_columns() -> None:
    ref = pd.DataFrame({"subjid": ["1", "2"], "aeterm": ["h", "n"], "only_ref": [1, 2]})
    actual = pd.DataFrame({"subjid": ["1", "2"], "aeterm": ["h", "n"], "only_act": [1, 2]})
    stats = build_candidate_stats(ref, actual)
    assert "subjid" in stats
    assert "aeterm" in stats
    assert "only_ref" not in stats
    assert "only_act" not in stats


def test_make_agent_azure_branch() -> None:
    """_make_agent uses AzureProvider when azure_openai_endpoint is set."""
    from unittest.mock import patch

    with (
        patch(
            "src.worker.engine.agents.recon_key_resolver.worker_settings",
            tensorzero_gateway_url="",
            azure_openai_endpoint="https://my.azure.openai.com",
            azure_openai_api_key="fake-key",
            openai_api_version="2024-05-01",
            llm_model="azure:gpt-4o",
        ),
        patch("src.worker.engine.agents.recon_key_resolver.AzureProvider") as mock_azure,
        patch("src.worker.engine.agents.recon_key_resolver.OpenAIChatModel"),
        patch("src.worker.engine.agents.recon_key_resolver.Agent") as mock_agent_cls,
    ):
        mock_agent_cls.return_value = MagicMock()
        from src.worker.engine.agents.recon_key_resolver import _make_agent

        _make_agent()
        mock_azure.assert_called_once()
