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


# ── DocumentationAgent tests (S09) ───────────────────────────────────────────


from src.worker.engine.agents.documentation import (  # noqa: E402
    DocumentationAgent,
    DocumentationError,
    DocumentationResult,
)
from src.worker.engine.models import JobContext, MacroVar  # noqa: E402


def _make_job_context() -> JobContext:
    return JobContext(
        source_files={"script.sas": "DATA out; SET in; RUN;"},
        resolved_macros=[
            MacroVar(name="DEPT", raw_value="SALES", source_file="script.sas", line=1)
        ],
        dependency_order=["in", "out"],
        risk_flags=["nested macro at script.sas:1"],
        blocks=[],
        generated=[],
    )


def _make_doc_run_result(markdown: str) -> MagicMock:
    mock = MagicMock()
    mock.output = DocumentationResult(markdown=markdown)
    return mock


@pytest.mark.asyncio
async def test_documentation_agent_generate_returns_markdown() -> None:
    """generate() returns the markdown string from the LLM result."""
    agent = DocumentationAgent()
    expected_md = "## Overview\n\nDoes ETL."
    agent._agent.run = AsyncMock(  # type: ignore[method-assign]
        return_value=_make_doc_run_result(expected_md)
    )

    result = await agent.generate(_make_job_context(), "out = inp.copy()", "3/3 checks passed.")

    assert result == expected_md


@pytest.mark.asyncio
async def test_documentation_agent_prompt_contains_source_and_code() -> None:
    """The prompt must include source files, generated code, and reconciliation summary."""
    agent = DocumentationAgent()
    run_mock = AsyncMock(return_value=_make_doc_run_result("# doc"))
    agent._agent.run = run_mock  # type: ignore[method-assign]

    await agent.generate(_make_job_context(), "out = inp.copy()", "2/3 checks passed.")

    prompt: str = run_mock.call_args[0][0]
    assert "script.sas" in prompt
    assert "DATA out; SET in; RUN;" in prompt
    assert "out = inp.copy()" in prompt
    assert "2/3 checks passed." in prompt


@pytest.mark.asyncio
async def test_documentation_agent_prompt_includes_macros_and_risk_flags() -> None:
    """Prompt must contain resolved macro variables and risk flags."""
    agent = DocumentationAgent()
    run_mock = AsyncMock(return_value=_make_doc_run_result("# doc"))
    agent._agent.run = run_mock  # type: ignore[method-assign]

    await agent.generate(_make_job_context(), "code", None)

    prompt: str = run_mock.call_args[0][0]
    assert "DEPT" in prompt
    assert "SALES" in prompt
    assert "nested macro" in prompt


@pytest.mark.asyncio
async def test_documentation_agent_uses_none_validation_result() -> None:
    """When validation_result is None, the prompt still renders without error."""
    agent = DocumentationAgent()
    run_mock = AsyncMock(return_value=_make_doc_run_result("# doc"))
    agent._agent.run = run_mock  # type: ignore[method-assign]

    result = await agent.generate(_make_job_context(), "code", None)

    prompt: str = run_mock.call_args[0][0]
    assert "Reconciliation not run." in prompt
    assert result == "# doc"


@pytest.mark.asyncio
async def test_documentation_agent_raises_on_llm_failure() -> None:
    """generate() must raise DocumentationError when the LLM call fails."""
    agent = DocumentationAgent()
    agent._agent.run = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("timeout")
    )

    with pytest.raises(DocumentationError) as exc_info:
        await agent.generate(_make_job_context(), "code", "1/3 checks passed.")

    assert isinstance(exc_info.value.cause, RuntimeError)


def test_documentation_agent_system_prompt_tagged() -> None:
    """System prompt must contain the agent tag."""
    from src.worker.engine.agents.documentation import _SYSTEM_PROMPT

    assert "# agent: DocumentationAgent" in _SYSTEM_PROMPT


def test_documentation_error_stores_cause() -> None:
    """DocumentationError must expose the cause attribute."""
    cause = RuntimeError("root")
    err = DocumentationError("failed", cause=cause)
    assert err.cause is cause
    assert "failed" in str(err)


def test_build_prompt_with_empty_dependency_order() -> None:
    """_build_prompt() renders 'N/A' when dependency_order is empty."""
    from src.worker.engine.agents.documentation import _build_prompt

    context = JobContext(
        source_files={"a.sas": "DATA x; RUN;"},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        blocks=[],
        generated=[],
    )
    prompt = _build_prompt(context, "code", None)
    assert "N/A" in prompt
    assert "Reconciliation not run." in prompt


def test_build_prompt_includes_all_sections() -> None:
    """_build_prompt() must include source files, macros, risk flags, code, and reconciliation."""
    from src.worker.engine.agents.documentation import _build_prompt

    context = _make_job_context()
    prompt = _build_prompt(context, "out = inp.copy()", "3/3 checks passed.")

    assert "script.sas" in prompt
    assert "DATA out; SET in; RUN;" in prompt
    assert "DEPT" in prompt
    assert "SALES" in prompt
    assert "nested macro" in prompt
    assert "out = inp.copy()" in prompt
    assert "3/3 checks passed." in prompt
    assert "in, out" in prompt
