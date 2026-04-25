"""Tests for ExplainAgent prompt composition and streaming."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.worker.engine.chatbot.explain_agent import (
    _AUDIENCE_PROMPTS,
    _BASE_SYSTEM_PROMPT,
    _MODE_PROMPTS,
    ExplainAgent,
    _build_system_prompt,
)


def test_build_system_prompt_contains_all_layers() -> None:
    prompt = _build_system_prompt("migration", "tech")
    assert _BASE_SYSTEM_PROMPT in prompt
    assert _MODE_PROMPTS["migration"] in prompt
    assert _AUDIENCE_PROMPTS["tech"] in prompt


def test_build_system_prompt_sas_general_non_tech() -> None:
    prompt = _build_system_prompt("sas_general", "non_tech")
    assert _MODE_PROMPTS["sas_general"] in prompt
    assert _AUDIENCE_PROMPTS["non_tech"] in prompt


def test_build_system_prompt_unknown_mode_falls_back() -> None:
    prompt = _build_system_prompt("unknown_mode", "tech")
    assert _MODE_PROMPTS["sas_general"] in prompt


def test_build_system_prompt_unknown_audience_falls_back() -> None:
    prompt = _build_system_prompt("migration", "unknown_audience")
    assert _AUDIENCE_PROMPTS["tech"] in prompt


def test_explain_agent_has_four_cached_agents() -> None:
    with patch("src.worker.engine.chatbot.explain_agent._make_agent", return_value=MagicMock()):
        agent = ExplainAgent()
    assert len(agent._agents) == 4
    assert ("migration", "tech") in agent._agents
    assert ("migration", "non_tech") in agent._agents
    assert ("sas_general", "tech") in agent._agents
    assert ("sas_general", "non_tech") in agent._agents


def test_get_agent_returns_correct_variant() -> None:
    mock_agents = {
        ("migration", "tech"): MagicMock(name="mig_tech"),
        ("migration", "non_tech"): MagicMock(name="mig_nontech"),
        ("sas_general", "tech"): MagicMock(name="sas_tech"),
        ("sas_general", "non_tech"): MagicMock(name="sas_nontech"),
    }
    with patch(
        "src.worker.engine.chatbot.explain_agent._make_agent", side_effect=lambda _: MagicMock()
    ):
        agent = ExplainAgent()
    agent._agents = mock_agents  # type: ignore[assignment]

    assert agent._get_agent("migration", "tech") is mock_agents[("migration", "tech")]
    assert agent._get_agent("sas_general", "non_tech") is mock_agents[("sas_general", "non_tech")]


def test_get_agent_unknown_combo_falls_back() -> None:
    fallback = MagicMock(name="fallback")
    mock_agents = {
        ("migration", "tech"): MagicMock(),
        ("migration", "non_tech"): MagicMock(),
        ("sas_general", "tech"): fallback,
        ("sas_general", "non_tech"): MagicMock(),
    }
    with patch(
        "src.worker.engine.chatbot.explain_agent._make_agent", side_effect=lambda _: MagicMock()
    ):
        agent = ExplainAgent()
    agent._agents = mock_agents  # type: ignore[assignment]

    assert agent._get_agent("invalid", "invalid") is fallback


@pytest.mark.asyncio
async def test_answer_stream_yields_chunks() -> None:
    async def fake_stream_text(delta: bool = False) -> AsyncGenerator[str, None]:
        yield "Hello "
        yield "world."

    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream.__aexit__ = AsyncMock(return_value=False)
    mock_stream.stream_text = fake_stream_text

    mock_inner_agent = MagicMock()
    mock_inner_agent.run_stream = MagicMock(return_value=mock_stream)

    with patch(
        "src.worker.engine.chatbot.explain_agent._make_agent", return_value=mock_inner_agent
    ):
        agent = ExplainAgent()

    chunks = []
    async for chunk in agent.answer_stream("test prompt", audience="tech", mode="migration"):
        chunks.append(chunk)

    assert chunks == ["Hello ", "world."]


@pytest.mark.asyncio
async def test_answer_stream_sas_general_mode() -> None:
    async def fake_stream_text(delta: bool = False) -> AsyncGenerator[str, None]:
        yield "SAS answer."

    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream.__aexit__ = AsyncMock(return_value=False)
    mock_stream.stream_text = fake_stream_text

    mock_inner_agent = MagicMock()
    mock_inner_agent.run_stream = MagicMock(return_value=mock_stream)

    with patch(
        "src.worker.engine.chatbot.explain_agent._make_agent",
        return_value=mock_inner_agent,
    ):
        agent = ExplainAgent()

    chunks = []
    async for chunk in agent.answer_stream(
        "What is PROC SORT?", audience="non_tech", mode="sas_general"
    ):
        chunks.append(chunk)

    assert chunks == ["SAS answer."]
