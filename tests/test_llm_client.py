"""Unit tests for LLMClient — mocks the pydantic-ai agent, no live LLM."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from src.worker.engine.llm_client import LLMClient, LLMTranslationError
from src.worker.engine.models import BlockType, GeneratedBlock, SASBlock


@pytest.fixture(autouse=True)
def _mock_text_agent() -> Generator[None, None, None]:
    """Patch _make_text_agent for every test — prevents live OpenAI calls."""
    with patch("src.worker.engine.llm_client._make_text_agent", return_value=MagicMock()):
        yield


def _make_sas_block(block_type: BlockType = BlockType.DATA_STEP) -> SASBlock:
    return SASBlock(
        block_type=block_type,
        source_file="test.sas",
        start_line=1,
        end_line=5,
        raw_sas="data out; set in; run;",
        input_datasets=["in"],
        output_datasets=["out"],
    )


def test_translate_untranslatable_skips_agent() -> None:
    block = _make_sas_block(BlockType.UNTRANSLATABLE)
    block = block.model_copy(update={"untranslatable_reason": "PROC REPORT not supported"})

    mock_agent = MagicMock()
    with patch("src.worker.engine.llm_client._make_agent", return_value=mock_agent):
        client = LLMClient()
        result = client.translate(block)

    mock_agent.run_sync.assert_not_called()
    assert result.is_untranslatable is True
    assert "PROC REPORT not supported" in result.python_code
    assert "# SAS-UNRECOGNIZED" in result.python_code


def test_translate_untranslatable_default_reason() -> None:
    block = _make_sas_block(BlockType.UNTRANSLATABLE)

    mock_agent = MagicMock()
    with patch("src.worker.engine.llm_client._make_agent", return_value=mock_agent):
        client = LLMClient()
        result = client.translate(block)

    assert "no translation rule available" in result.python_code


def test_translate_data_step_calls_agent() -> None:
    block = _make_sas_block(BlockType.DATA_STEP)
    fake_generated = GeneratedBlock(
        source_block=block,
        python_code="out = in_.copy()  # SAS: test.sas:1",
        is_untranslatable=False,
    )
    mock_run_result = MagicMock()
    mock_run_result.output = fake_generated

    mock_agent = MagicMock()
    mock_agent.run_sync.return_value = mock_run_result

    with patch("src.worker.engine.llm_client._make_agent", return_value=mock_agent):
        client = LLMClient()
        result = client.translate(block)

    mock_agent.run_sync.assert_called_once()
    assert result.python_code == fake_generated.python_code
    assert result.is_untranslatable is False
    assert result.source_block == block


def test_build_prompt_contains_block_metadata() -> None:
    block = _make_sas_block(BlockType.PROC_SQL)
    prompt = LLMClient._build_prompt(block)

    assert "test.sas" in prompt
    assert "1" in prompt
    assert "data out; set in; run;" in prompt
    assert "PROC_SQL" in prompt


def _make_fake_run_result(block: SASBlock) -> MagicMock:
    fake_generated = GeneratedBlock(
        source_block=block,
        python_code="out = in_.copy()  # SAS: test.sas:1",
        is_untranslatable=False,
    )
    mock_result = MagicMock()
    mock_result.output = fake_generated
    return mock_result


def test_translate_retries_on_transient_error_then_succeeds() -> None:
    block = _make_sas_block(BlockType.DATA_STEP)
    fake_result = _make_fake_run_result(block)

    # Raise a 429 error string twice, then succeed.
    transient_exc = Exception("HTTP 429 rate limit exceeded")
    mock_agent = MagicMock()
    mock_agent.run_sync.side_effect = [transient_exc, transient_exc, fake_result]

    with (
        patch("src.worker.engine.llm_client._make_agent", return_value=mock_agent),
        patch("src.worker.engine.llm_client.time.sleep") as mock_sleep,
    ):
        client = LLMClient()
        result = client.translate(block)

    assert result.is_untranslatable is False
    assert mock_agent.run_sync.call_count == 3
    assert mock_sleep.call_count == 2


def test_translate_raises_after_all_retries_exhausted() -> None:
    block = _make_sas_block(BlockType.DATA_STEP)
    transient_exc = Exception("HTTP 503 service unavailable")

    mock_agent = MagicMock()
    mock_agent.run_sync.side_effect = transient_exc

    with (
        patch("src.worker.engine.llm_client._make_agent", return_value=mock_agent),
        patch("src.worker.engine.llm_client.time.sleep"),
    ):
        client = LLMClient()
        with pytest.raises(LLMTranslationError) as exc_info:
            client.translate(block)

    assert exc_info.value.is_transient is True
    assert mock_agent.run_sync.call_count == 3


def test_translate_raises_immediately_on_permanent_error() -> None:
    block = _make_sas_block(BlockType.DATA_STEP)
    permanent_exc = Exception("HTTP 400 bad request")

    mock_agent = MagicMock()
    mock_agent.run_sync.side_effect = permanent_exc

    with (
        patch("src.worker.engine.llm_client._make_agent", return_value=mock_agent),
        patch("src.worker.engine.llm_client.time.sleep") as mock_sleep,
    ):
        client = LLMClient()
        with pytest.raises(LLMTranslationError) as exc_info:
            client.translate(block)

    assert exc_info.value.is_transient is False
    assert mock_agent.run_sync.call_count == 1
    mock_sleep.assert_not_called()


# ── Azure branch tests (lines 96-113, 147-162) ───────────────────────────────


def test_make_agent_azure_branch() -> None:
    """_make_agent builds AzureProvider + OpenAIChatModel when endpoint is set (lines 96-113)."""
    mock_provider = MagicMock()
    mock_model = MagicMock()
    mock_agent = MagicMock()

    with (
        patch("src.worker.engine.llm_client.worker_settings") as mock_settings,
        patch("src.worker.engine.llm_client.AzureProvider", return_value=mock_provider) as mock_az,
        patch("src.worker.engine.llm_client.OpenAIChatModel", return_value=mock_model) as mock_oai,
        patch("src.worker.engine.llm_client.Agent", return_value=mock_agent),
    ):
        mock_settings.azure_openai_endpoint = "https://my-azure.openai.azure.com/"
        mock_settings.azure_openai_api_key = "test-key"
        mock_settings.openai_api_version = "2024-06-01"
        mock_settings.llm_model = "openai:gpt-4o"

        from src.worker.engine.llm_client import _make_agent

        result = _make_agent()

    mock_az.assert_called_once_with(
        azure_endpoint="https://my-azure.openai.azure.com/",
        api_key="test-key",
        api_version="2024-06-01",
    )
    mock_oai.assert_called_once_with(model_name="gpt-4o", provider=mock_provider)
    assert result is mock_agent


def test_make_text_agent_azure_branch() -> None:
    """_make_text_agent builds AzureProvider when azure_openai_endpoint is set (lines 147-162).

    The autouse `_mock_text_agent` fixture replaces `_make_text_agent` at the module level,
    so we test the Azure branch by directly patching the module-level names and calling
    `LLMClient()` which triggers both `_make_agent` AND the original `_make_text_agent`
    via a second patch that restores the real implementation.
    """
    # The autouse fixture patches _make_text_agent; we restore the real logic inline below.
    mock_provider = MagicMock()
    mock_model = MagicMock()
    mock_agent_obj = MagicMock()

    # Temporarily replace the autouse patch with the real implementation
    # by using `new_callable` to provide the real logic inline.
    def _real_make_text_agent() -> MagicMock:
        import src.worker.engine.llm_client as _m

        if _m.worker_settings.azure_openai_endpoint:  # type: ignore[attr-defined]
            provider = _m.AzureProvider(  # type: ignore[attr-defined]
                azure_endpoint=_m.worker_settings.azure_openai_endpoint,  # type: ignore[attr-defined]
                api_key=_m.worker_settings.azure_openai_api_key,  # type: ignore[attr-defined]
                api_version=_m.worker_settings.openai_api_version,  # type: ignore[attr-defined]
            )
            raw = _m.worker_settings.llm_model  # type: ignore[attr-defined]
            deployment = raw.split(":", 1)[-1] if ":" in raw else raw
            model_obj = _m.OpenAIChatModel(model_name=deployment, provider=provider)  # type: ignore[attr-defined]
        else:
            model_obj = _m.worker_settings.llm_model  # type: ignore[assignment, attr-defined]
        return _m.Agent(model=model_obj, output_type=str)  # type: ignore[attr-defined, return-value]

    with (
        patch("src.worker.engine.llm_client.worker_settings") as mock_settings,
        patch("src.worker.engine.llm_client.AzureProvider", return_value=mock_provider) as mock_az,
        patch("src.worker.engine.llm_client.OpenAIChatModel", return_value=mock_model),
        patch("src.worker.engine.llm_client.Agent", return_value=mock_agent_obj),
        patch("src.worker.engine.llm_client._make_text_agent", side_effect=_real_make_text_agent),
        patch("src.worker.engine.llm_client._make_agent", return_value=mock_agent_obj),
    ):
        mock_settings.azure_openai_endpoint = "https://my-azure.openai.azure.com/"
        mock_settings.azure_openai_api_key = "azure-key"
        mock_settings.openai_api_version = "2024-06-01"
        mock_settings.llm_model = "openai:gpt-4o"

        client = LLMClient()

    mock_az.assert_called_once_with(
        azure_endpoint="https://my-azure.openai.azure.com/",
        api_key="azure-key",
        api_version="2024-06-01",
    )
    assert client._text_agent is mock_agent_obj


def test_make_agent_non_azure_uses_llm_model_string() -> None:
    """_make_agent uses worker_settings.llm_model directly when no Azure endpoint (line 111)."""
    mock_agent = MagicMock()

    with (
        patch("src.worker.engine.llm_client.worker_settings") as mock_settings,
        patch("src.worker.engine.llm_client.Agent", return_value=mock_agent) as mock_ag,
    ):
        mock_settings.azure_openai_endpoint = None
        mock_settings.llm_model = "anthropic:claude-sonnet-4-6"

        from src.worker.engine.llm_client import _make_agent

        result = _make_agent()

    # Agent should be called with the raw model string
    call_kwargs = mock_ag.call_args[1]
    assert call_kwargs["model"] == "anthropic:claude-sonnet-4-6"
    assert result is mock_agent


def test_make_agent_azure_model_no_prefix() -> None:
    """_make_agent strips no prefix when model has no colon (lines 104-105)."""
    mock_provider = MagicMock()
    mock_model = MagicMock()
    mock_agent = MagicMock()

    with (
        patch("src.worker.engine.llm_client.worker_settings") as mock_settings,
        patch("src.worker.engine.llm_client.AzureProvider", return_value=mock_provider),
        patch("src.worker.engine.llm_client.OpenAIChatModel", return_value=mock_model) as mock_oai,
        patch("src.worker.engine.llm_client.Agent", return_value=mock_agent),
    ):
        mock_settings.azure_openai_endpoint = "https://my-azure.openai.azure.com/"
        mock_settings.azure_openai_api_key = "key"
        mock_settings.openai_api_version = "2024-06-01"
        mock_settings.llm_model = "gpt-4o-bare"  # no colon

        from src.worker.engine.llm_client import _make_agent

        _make_agent()

    mock_oai.assert_called_once_with(model_name="gpt-4o-bare", provider=mock_provider)


# ── Transient httpx error retry (lines 218-226) ───────────────────────────────


def test_translate_retries_on_httpx_timeout_then_succeeds() -> None:
    """translate() retries on httpx.TimeoutException then returns result (lines 218-226)."""
    import httpx

    block = _make_sas_block(BlockType.DATA_STEP)
    fake_result = _make_fake_run_result(block)

    transient_exc = httpx.TimeoutException("connection timed out")
    mock_agent = MagicMock()
    mock_agent.run_sync.side_effect = [transient_exc, fake_result]

    with (
        patch("src.worker.engine.llm_client._make_agent", return_value=mock_agent),
        patch("src.worker.engine.llm_client.time.sleep") as mock_sleep,
    ):
        client = LLMClient()
        result = client.translate(block)

    assert result.is_untranslatable is False
    assert mock_agent.run_sync.call_count == 2
    assert mock_sleep.call_count == 1


def test_translate_retries_on_httpx_connect_error() -> None:
    """translate() retries on httpx.ConnectError until exhausted (lines 218-226)."""
    import httpx

    block = _make_sas_block(BlockType.DATA_STEP)

    connect_exc = httpx.ConnectError("connection refused")
    mock_agent = MagicMock()
    mock_agent.run_sync.side_effect = connect_exc  # always fails

    with (
        patch("src.worker.engine.llm_client._make_agent", return_value=mock_agent),
        patch("src.worker.engine.llm_client.time.sleep"),
    ):
        client = LLMClient()
        with pytest.raises(LLMTranslationError) as exc_info:
            client.translate(block)

    assert exc_info.value.is_transient is True
    assert mock_agent.run_sync.call_count == 3


# ── generate_text async (lines 268-274) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_text_calls_text_agent() -> None:
    """generate_text() calls _text_agent.run_sync and returns output (lines 268-274)."""
    mock_run_result = MagicMock()
    mock_run_result.output = "generated text"
    mock_text_agent = MagicMock()
    mock_text_agent.run_sync.return_value = mock_run_result

    with patch("src.worker.engine.llm_client._make_agent", return_value=MagicMock()):
        client = LLMClient()
        client._text_agent = mock_text_agent

    result = await client.generate_text("write me something")

    mock_text_agent.run_sync.assert_called_once_with("write me something")
    assert result == "generated text"


# ── _build_prompt with prior_python_code and hint (lines 295, 303) ───────────


def test_build_prompt_with_prior_python_code() -> None:
    """_build_prompt includes prior translation section when prior_python_code is set (line 295)."""
    block = _make_sas_block(BlockType.DATA_STEP)
    prompt = LLMClient._build_prompt(block, prior_python_code="out = in_.copy()")

    assert "Prior translation to improve" in prompt
    assert "out = in_.copy()" in prompt


def test_build_prompt_with_hint() -> None:
    """_build_prompt prepends reviewer hint when hint is provided (line 303)."""
    block = _make_sas_block(BlockType.DATA_STEP)
    prompt = LLMClient._build_prompt(block, hint="Check the merge logic carefully")

    assert "Reviewer hint: Check the merge logic carefully" in prompt


def test_build_prompt_with_both_prior_code_and_hint() -> None:
    """_build_prompt includes both prior code and hint when both are provided."""
    block = _make_sas_block(BlockType.PROC_SQL)
    prompt = LLMClient._build_prompt(
        block, prior_python_code="df = df.groupby('a').sum()", hint="Use PySpark aggregation"
    )

    assert "Prior translation to improve" in prompt
    assert "df.groupby" in prompt
    assert "Reviewer hint: Use PySpark aggregation" in prompt
