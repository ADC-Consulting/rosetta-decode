"""Unit tests for LLMClient — mocks the pydantic-ai agent, no live LLM."""

from unittest.mock import MagicMock, patch

from src.worker.engine.llm_client import LLMClient
from src.worker.engine.models import BlockType, GeneratedBlock, SASBlock


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
    assert "# SAS-UNTRANSLATABLE" in result.python_code


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
