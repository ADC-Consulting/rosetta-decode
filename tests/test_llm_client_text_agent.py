"""Tests for _make_text_agent Azure branch — separate file to avoid autouse fixture."""

# SAS: tests/test_llm_client_text_agent.py:1

from unittest.mock import MagicMock, patch


def test_make_text_agent_azure_branch_real_function() -> None:
    """_make_text_agent builds AzureProvider when azure_openai_endpoint is set (lines 147-162)."""
    mock_provider = MagicMock()
    mock_model = MagicMock()
    mock_agent = MagicMock()

    with (
        patch("src.worker.engine.llm_client.worker_settings") as mock_settings,
        patch("src.worker.engine.llm_client.AzureProvider", return_value=mock_provider) as mock_az,
        patch("src.worker.engine.llm_client.OpenAIChatModel", return_value=mock_model),
        patch("src.worker.engine.llm_client.Agent", return_value=mock_agent),
    ):
        mock_settings.azure_openai_endpoint = "https://my-azure.openai.azure.com/"
        mock_settings.azure_openai_api_key = "azure-key"
        mock_settings.openai_api_version = "2024-06-01"
        mock_settings.llm_model = "openai:gpt-4o"

        from src.worker.engine.llm_client import _make_text_agent

        result = _make_text_agent()

    mock_az.assert_called_once_with(
        azure_endpoint="https://my-azure.openai.azure.com/",
        api_key="azure-key",
        api_version="2024-06-01",
    )
    assert result is mock_agent


def test_make_text_agent_non_azure_uses_llm_model_string() -> None:
    """_make_text_agent uses llm_model directly when no Azure endpoint (line 160)."""
    mock_agent = MagicMock()

    with (
        patch("src.worker.engine.llm_client.worker_settings") as mock_settings,
        patch("src.worker.engine.llm_client.Agent", return_value=mock_agent) as mock_ag,
    ):
        mock_settings.azure_openai_endpoint = None
        mock_settings.llm_model = "anthropic:claude-sonnet-4-6"

        from src.worker.engine.llm_client import _make_text_agent

        result = _make_text_agent()

    call_kwargs = mock_ag.call_args[1]
    assert call_kwargs["model"] == "anthropic:claude-sonnet-4-6"
    assert result is mock_agent
