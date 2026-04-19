"""Unit tests for src/worker/engine/doc_generator.py."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.worker.engine.doc_generator import DocGenerator, _build_doc_prompt


def _make_job(
    files: dict[str, str] | None = None,
    report: dict[str, object] | None = None,
) -> MagicMock:
    job = MagicMock()
    job.id = "test-job-id"
    job.files = files if files is not None else {"script.sas": "data out; set in; run;"}
    job.report = report
    return job


def test_build_doc_prompt_includes_source() -> None:
    prompt = _build_doc_prompt({"script.sas": "data out; run;"}, None)
    assert "script.sas" in prompt
    assert "data out; run;" in prompt
    assert "No reconciliation report available." in prompt


def test_build_doc_prompt_with_report_shows_checks() -> None:
    report = {"checks": [{"status": "pass"}, {"status": "pass"}, {"status": "fail"}]}
    prompt = _build_doc_prompt({"a.sas": "x"}, report)
    assert "2/3 checks passed" in prompt


def test_build_doc_prompt_empty_report_checks() -> None:
    prompt = _build_doc_prompt({"a.sas": "x"}, {"checks": []})
    assert "0/0 checks passed" in prompt


@pytest.mark.asyncio
async def test_generate_returns_doc_string() -> None:
    job = _make_job()
    llm_client = AsyncMock()
    llm_client.generate_text = AsyncMock(return_value="## Summary\n\nDoes ETL.")

    result = await DocGenerator().generate(job, llm_client)

    assert result == "## Summary\n\nDoes ETL."
    llm_client.generate_text.assert_called_once()


@pytest.mark.asyncio
async def test_generate_returns_none_when_no_files() -> None:
    job = _make_job(files={})
    llm_client = AsyncMock()

    result = await DocGenerator().generate(job, llm_client)

    assert result is None
    llm_client.generate_text.assert_not_called()


@pytest.mark.asyncio
async def test_generate_filters_sentinel_keys() -> None:
    job = _make_job(files={"__ref_csv_data.csv__": "...", "script.sas": "data out; run;"})
    llm_client = AsyncMock()
    llm_client.generate_text = AsyncMock(return_value="doc")

    await DocGenerator().generate(job, llm_client)

    call_args = llm_client.generate_text.call_args[0][0]
    assert "script.sas" in call_args
    assert "__ref_csv_data.csv__" not in call_args


@pytest.mark.asyncio
async def test_generate_returns_none_on_llm_exception() -> None:
    job = _make_job()
    llm_client = AsyncMock()
    llm_client.generate_text = AsyncMock(side_effect=RuntimeError("LLM down"))

    result = await DocGenerator().generate(job, llm_client)

    assert result is None


@pytest.mark.asyncio
async def test_generate_returns_none_when_files_all_sentinels() -> None:
    job = _make_job(files={"__ref_csv__": "data", "__sentinel__": "x"})
    llm_client = AsyncMock()

    result = await DocGenerator().generate(job, llm_client)

    assert result is None
    llm_client.generate_text.assert_not_called()
