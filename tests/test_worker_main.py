"""Unit tests for src/worker/main.py — mocks DB session and engine components."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from src.backend.db.models import Job
from src.worker.main import (
    JobOrchestrator,
    _claim_job,
    _dict_to_recon_report,
    _process_job,
    _recon_summary,
)


def _make_job(**kwargs: object) -> Job:
    job = Job(
        id="test-job-id",
        status="queued",
        input_hash="abc",
        files={"test.sas": "data out; set in; run;"},
    )
    for k, v in kwargs.items():
        setattr(job, k, v)
    return job


@pytest.mark.asyncio
async def test_claim_job_returns_none_when_queue_empty() -> None:
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    job = await _claim_job(session)

    assert job is None
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_claim_job_returns_job_and_commits() -> None:
    fake_job = _make_job()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = fake_job
    session.execute.return_value = result_mock

    job = await _claim_job(session)

    assert job is fake_job
    session.commit.assert_called_once()
    session.refresh.assert_called_once_with(fake_job)


@pytest.mark.asyncio
async def test_process_job_success_sets_status_done() -> None:
    fake_job = _make_job()
    session = AsyncMock()

    fake_blocks = [MagicMock()]
    fake_generated = [MagicMock()]
    fake_code = "result = df.copy()  # SAS: test.sas:1"
    fake_report: dict[str, list[object]] = {"checks": []}

    with (
        patch("src.worker.main.SASParser") as mock_parser,
        patch("src.worker.main.LLMClient") as mock_client,
        patch("src.worker.main.CodeGenerator") as mock_codegen,
        patch("src.worker.main.ReconciliationService"),
        patch("src.worker.main.BackendFactory") as mock_factory,
        patch("src.worker.main.asyncio.to_thread") as mock_to_thread,
        patch("src.worker.main.DocGenerator") as mock_doc,
        patch("src.worker.main.extract_lineage", return_value={"nodes": [], "edges": []}),
    ):
        mock_parser.return_value.parse.return_value = MagicMock(blocks=fake_blocks, macro_vars={})
        mock_client.return_value.translate.return_value = fake_generated[0]
        mock_codegen.return_value.assemble.return_value = fake_code
        mock_factory.create.return_value = MagicMock()
        mock_to_thread.side_effect = [fake_generated[0], fake_report]
        mock_doc.return_value.generate = AsyncMock(return_value="## Summary")

        await _process_job(session, fake_job)

    assert session.execute.call_count == 1
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_process_job_success_doc_failure_does_not_crash() -> None:
    """Doc generation failure should be swallowed and job still marked done."""
    fake_job = _make_job()
    session = AsyncMock()
    fake_report: dict[str, list[object]] = {"checks": []}

    with (
        patch("src.worker.main.SASParser") as mock_parser,
        patch("src.worker.main.LLMClient") as mock_client,
        patch("src.worker.main.CodeGenerator") as mock_codegen,
        patch("src.worker.main.ReconciliationService"),
        patch("src.worker.main.BackendFactory") as mock_factory,
        patch("src.worker.main.asyncio.to_thread") as mock_to_thread,
        patch("src.worker.main.DocGenerator") as mock_doc,
        patch("src.worker.main.extract_lineage", return_value=None),
    ):
        fake_block = MagicMock()
        mock_parser.return_value.parse.return_value = MagicMock(blocks=[fake_block], macro_vars={})
        mock_client.return_value.translate.return_value = fake_block
        mock_codegen.return_value.assemble.return_value = "code"
        mock_factory.create.return_value = MagicMock()
        mock_to_thread.side_effect = [fake_block, fake_report]
        mock_doc.return_value.generate = AsyncMock(side_effect=RuntimeError("LLM down"))

        await _process_job(session, fake_job)

    assert session.execute.call_count == 1
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_process_job_lineage_failure_does_not_crash() -> None:
    """Lineage extraction failure should be swallowed and job still proceeds."""
    fake_job = _make_job()
    session = AsyncMock()
    fake_report: dict[str, list[object]] = {"checks": []}

    with (
        patch("src.worker.main.SASParser") as mock_parser,
        patch("src.worker.main.LLMClient") as mock_client,
        patch("src.worker.main.CodeGenerator") as mock_codegen,
        patch("src.worker.main.ReconciliationService"),
        patch("src.worker.main.BackendFactory") as mock_factory,
        patch("src.worker.main.asyncio.to_thread") as mock_to_thread,
        patch("src.worker.main.DocGenerator") as mock_doc,
        patch("src.worker.main.extract_lineage", side_effect=RuntimeError("lineage boom")),
    ):
        fake_block = MagicMock()
        mock_parser.return_value.parse.return_value = MagicMock(blocks=[fake_block], macro_vars={})
        mock_client.return_value.translate.return_value = fake_block
        mock_codegen.return_value.assemble.return_value = "code"
        mock_factory.create.return_value = MagicMock()
        mock_to_thread.side_effect = [fake_block, fake_report]
        mock_doc.return_value.generate = AsyncMock(return_value=None)

        await _process_job(session, fake_job)

    assert session.execute.call_count == 1
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_process_job_failure_sets_status_failed() -> None:
    fake_job = _make_job()
    session = AsyncMock()

    with patch("src.worker.main.SASParser") as mock_parser:
        mock_parser.return_value.parse.side_effect = RuntimeError("parse exploded")
        await _process_job(session, fake_job)

    # Failure path: execute called once (UPDATE to failed), commit called once
    assert session.execute.call_count == 1
    session.commit.assert_called_once()


# ── _recon_summary ────────────────────────────────────────────────────────────


def test_recon_summary_none_returns_none() -> None:
    assert _recon_summary(None) is None


def test_recon_summary_dict_with_checks() -> None:
    report = {"checks": [{"status": "pass"}, {"status": "pass"}, {"status": "fail"}]}
    result = _recon_summary(report)
    assert result == "2/3 checks passed."


def test_recon_summary_empty_dict_checks() -> None:
    result = _recon_summary({"checks": []})
    assert result == "0/0 checks passed."


def test_recon_summary_reconciliation_report_passed() -> None:
    report = MagicMock()
    report.passed = True
    report.diff_summary = ""
    result = _recon_summary(report)
    assert result == "Reconciliation passed. "


def test_recon_summary_reconciliation_report_failed() -> None:
    report = MagicMock()
    report.passed = False
    report.diff_summary = "row 1 differs"
    result = _recon_summary(report)
    assert result == "Reconciliation failed. row 1 differs"


# ── JobOrchestrator helpers ───────────────────────────────────────────────────


def _make_orchestrator_with_mocks() -> tuple[JobOrchestrator, dict[str, MagicMock]]:
    """Build a JobOrchestrator with all agent/component attributes replaced by mocks."""
    with (
        patch("src.worker.main.AnalysisAgent"),
        patch("src.worker.main.DataStepAgent"),
        patch("src.worker.main.ProcAgent"),
        patch("src.worker.main.StubGenerator"),
        patch("src.worker.main.TranslationRouter"),
        patch("src.worker.main.CodeGenerator"),
        patch("src.worker.main.ReconciliationService"),
        patch("src.worker.main.FailureInterpreterAgent"),
        patch("src.worker.main.DocumentationAgent"),
        patch("src.worker.main.MacroExpander"),
        patch("src.worker.main.MigrationPlannerAgent"),
    ):
        orch = JobOrchestrator()

    mocks: dict[str, MagicMock] = {}
    mocks["analysis"] = MagicMock()
    mocks["analysis"].analyse = AsyncMock()
    mocks["router"] = MagicMock()
    mocks["codegen"] = MagicMock()
    mocks["reconciler"] = MagicMock()
    mocks["failure_interpreter"] = MagicMock()
    mocks["failure_interpreter"].interpret = AsyncMock()
    mocks["doc_agent"] = MagicMock()
    mocks["doc_agent"].generate = AsyncMock()
    mocks["expander"] = MagicMock()
    mocks["migration_planner"] = MagicMock()
    mocks["migration_planner"].plan = AsyncMock(return_value=MagicMock(block_plans=[]))

    orch._analysis_agent = mocks["analysis"]
    orch._router = mocks["router"]
    orch._codegen = mocks["codegen"]
    orch._reconciler = mocks["reconciler"]
    orch._failure_interpreter = mocks["failure_interpreter"]
    orch._doc_agent = mocks["doc_agent"]
    orch._expander = mocks["expander"]
    orch._migration_planner = mocks["migration_planner"]

    return orch, mocks


def _make_fake_context() -> MagicMock:
    ctx = MagicMock()
    ctx.resolved_macros = []
    ctx.risk_flags = []
    ctx.model_copy = MagicMock(return_value=ctx)
    return ctx


def _make_fake_block(source_file: str = "test.sas", start_line: int = 1) -> MagicMock:
    block = MagicMock()
    block.source_file = source_file
    block.start_line = start_line
    return block


def _make_fake_generated_block() -> MagicMock:
    return MagicMock()


def _make_fake_report(passed: bool = True, diff_summary: str = "") -> MagicMock:
    report = MagicMock()
    report.passed = passed
    report.diff_summary = diff_summary
    return report


# ── JobOrchestrator.run() ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_run_delegates_to_execute() -> None:
    """run() should call _execute and not catch anything on success."""
    orch, _ = _make_orchestrator_with_mocks()
    orch._execute = AsyncMock()  # type: ignore[method-assign]
    session = AsyncMock()
    job = _make_job()

    await orch.run(session, job)

    orch._execute.assert_called_once_with(session, job)


@pytest.mark.asyncio
async def test_orchestrator_run_handles_http_429() -> None:
    """HTTP 429 causes job to be marked failed with circuit_breaker_tripped."""
    orch, _ = _make_orchestrator_with_mocks()
    session = AsyncMock()
    job = _make_job()

    response_mock = MagicMock()
    response_mock.status_code = 429
    http_err = httpx.HTTPStatusError("429", request=MagicMock(), response=response_mock)
    orch._execute = AsyncMock(side_effect=http_err)  # type: ignore[method-assign]

    await orch.run(session, job)

    session.execute.assert_called_once()
    session.commit.assert_called_once()
    call_kwargs = session.execute.call_args
    assert call_kwargs is not None


@pytest.mark.asyncio
async def test_orchestrator_run_handles_generic_exception() -> None:
    """Generic exception causes job to be marked failed."""
    orch, _ = _make_orchestrator_with_mocks()
    session = AsyncMock()
    job = _make_job()
    orch._execute = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

    await orch.run(session, job)

    session.execute.assert_called_once()
    session.commit.assert_called_once()


# ── JobOrchestrator._execute() ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_execute_success() -> None:
    """Full happy-path execute sets job to done."""
    orch, mocks = _make_orchestrator_with_mocks()
    session = AsyncMock()
    job = _make_job(files={"test.sas": "DATA out; SET in; RUN;"})

    fake_block = _make_fake_block()
    fake_gb = _make_fake_generated_block()
    fake_ctx = _make_fake_context()
    fake_report = _make_fake_report(passed=True)

    parse_result = MagicMock()
    parse_result.blocks = [fake_block]
    parse_result.macro_vars = []

    mocks["expander"].expand.return_value = [fake_block]
    mocks["analysis"].analyse = AsyncMock(return_value=fake_ctx)

    translator_mock = MagicMock()
    translator_mock.translate = AsyncMock(return_value=fake_gb)
    mocks["router"].route.return_value = translator_mock

    mocks["codegen"].assemble.return_value = "result = df.copy()"
    mocks["reconciler"].run.return_value = fake_report
    mocks["doc_agent"].generate = AsyncMock(return_value="## Docs")

    with (
        patch("src.worker.main.SASParser") as mock_parser,
        patch("src.worker.main.BackendFactory") as mock_factory,
        patch("src.worker.main.asyncio.to_thread", new=AsyncMock(return_value=fake_report)),
        patch("src.worker.main.extract_lineage", return_value={"nodes": [], "edges": []}),
    ):
        mock_parser.return_value.parse.return_value = parse_result
        mock_factory.create.return_value = MagicMock()

        await orch._execute(session, job)

    session.execute.assert_called_once()
    # Two commits: one for the main job persist, one for auto-saved version rows.
    assert session.commit.call_count == 2


@pytest.mark.asyncio
async def test_orchestrator_execute_doc_failure_swallowed() -> None:
    """Doc generation failure is swallowed; job still completes."""
    orch, mocks = _make_orchestrator_with_mocks()
    session = AsyncMock()
    job = _make_job(files={"test.sas": "DATA out; SET in; RUN;"})

    fake_block = _make_fake_block()
    fake_gb = _make_fake_generated_block()
    fake_ctx = _make_fake_context()
    fake_report = _make_fake_report(passed=True)

    parse_result = MagicMock()
    parse_result.blocks = [fake_block]
    parse_result.macro_vars = []

    mocks["expander"].expand.return_value = [fake_block]
    mocks["analysis"].analyse = AsyncMock(return_value=fake_ctx)

    translator_mock = MagicMock()
    translator_mock.translate = AsyncMock(return_value=fake_gb)
    mocks["router"].route.return_value = translator_mock
    mocks["codegen"].assemble.return_value = "code"
    mocks["doc_agent"].generate = AsyncMock(side_effect=RuntimeError("doc boom"))

    with (
        patch("src.worker.main.SASParser") as mock_parser,
        patch("src.worker.main.BackendFactory") as mock_factory,
        patch("src.worker.main.asyncio.to_thread", new=AsyncMock(return_value=fake_report)),
        patch("src.worker.main.extract_lineage", return_value=None),
    ):
        mock_parser.return_value.parse.return_value = parse_result
        mock_factory.create.return_value = MagicMock()

        await orch._execute(session, job)

    session.execute.assert_called_once()
    assert session.commit.call_count == 2


@pytest.mark.asyncio
async def test_orchestrator_execute_lineage_failure_swallowed() -> None:
    """Lineage extraction failure is swallowed; job still completes."""
    orch, mocks = _make_orchestrator_with_mocks()
    session = AsyncMock()
    job = _make_job(files={"test.sas": "DATA out; SET in; RUN;"})

    fake_block = _make_fake_block()
    fake_gb = _make_fake_generated_block()
    fake_ctx = _make_fake_context()
    fake_report = _make_fake_report(passed=True)

    parse_result = MagicMock()
    parse_result.blocks = [fake_block]
    parse_result.macro_vars = []

    mocks["expander"].expand.return_value = [fake_block]
    mocks["analysis"].analyse = AsyncMock(return_value=fake_ctx)

    translator_mock = MagicMock()
    translator_mock.translate = AsyncMock(return_value=fake_gb)
    mocks["router"].route.return_value = translator_mock
    mocks["codegen"].assemble.return_value = "code"
    mocks["doc_agent"].generate = AsyncMock(return_value=None)

    with (
        patch("src.worker.main.SASParser") as mock_parser,
        patch("src.worker.main.BackendFactory") as mock_factory,
        patch("src.worker.main.asyncio.to_thread", new=AsyncMock(return_value=fake_report)),
        patch("src.worker.main.extract_lineage", side_effect=RuntimeError("lineage boom")),
    ):
        mock_parser.return_value.parse.return_value = parse_result
        mock_factory.create.return_value = MagicMock()

        await orch._execute(session, job)

    session.execute.assert_called_once()


# ── JobOrchestrator._translate_two_phase() ───────────────────────────────────


@pytest.mark.asyncio
async def test_translate_with_refinement_passes_first_try() -> None:
    """When reconciliation passes immediately, no retry is attempted."""
    orch, mocks = _make_orchestrator_with_mocks()
    fake_block = _make_fake_block()
    fake_gb = _make_fake_generated_block()
    fake_ctx = _make_fake_context()
    fake_report = _make_fake_report(passed=True)

    translator_mock = MagicMock()
    translator_mock.translate = AsyncMock(return_value=fake_gb)
    mocks["router"].route.return_value = translator_mock
    mocks["codegen"].assemble.return_value = "code"
    mocks["reconciler"].run.return_value = fake_report

    with (
        patch("src.worker.main.BackendFactory") as mock_factory,
        patch("src.worker.main.asyncio.to_thread", new=AsyncMock(return_value=fake_report)),
    ):
        mock_factory.create.return_value = MagicMock()
        result = await orch._translate_two_phase([fake_block], fake_ctx, "", "")

    assert result == [fake_gb]
    mocks["failure_interpreter"].interpret.assert_not_called()


@pytest.mark.asyncio
async def test_translate_with_refinement_retries_on_failure() -> None:
    """When reconciliation fails with a diff, failure interpreter is called."""
    orch, mocks = _make_orchestrator_with_mocks()
    fake_block = _make_fake_block(source_file="test.sas", start_line=1)
    fake_gb = _make_fake_generated_block()
    fake_ctx = _make_fake_context()

    failed_report = _make_fake_report(passed=False, diff_summary="row 1 differs")
    passed_report = _make_fake_report(passed=True)

    translator_mock = MagicMock()
    translator_mock.translate = AsyncMock(return_value=fake_gb)
    mocks["router"].route.return_value = translator_mock
    mocks["codegen"].assemble.return_value = "code"
    mocks["failure_interpreter"].interpret = AsyncMock(
        return_value=("fix the rounding", "test.sas:1")
    )

    reports = iter([failed_report, passed_report])

    async def _fake_to_thread(fn: object, *args: object) -> object:
        return next(reports)

    with (
        patch("src.worker.main.BackendFactory") as mock_factory,
        patch("src.worker.main.asyncio.to_thread", side_effect=_fake_to_thread),
    ):
        mock_factory.create.return_value = MagicMock()
        result = await orch._translate_two_phase([fake_block], fake_ctx, "", "")

    mocks["failure_interpreter"].interpret.assert_called_once()
    assert len(result) == 1


@pytest.mark.asyncio
async def test_translate_with_refinement_breaks_on_no_diff_summary() -> None:
    """When reconciliation fails but diff_summary is empty, no retry is attempted."""
    orch, mocks = _make_orchestrator_with_mocks()
    fake_block = _make_fake_block()
    fake_gb = _make_fake_generated_block()
    fake_ctx = _make_fake_context()
    failed_report = _make_fake_report(passed=False, diff_summary="")

    translator_mock = MagicMock()
    translator_mock.translate = AsyncMock(return_value=fake_gb)
    mocks["router"].route.return_value = translator_mock
    mocks["codegen"].assemble.return_value = "code"

    with (
        patch("src.worker.main.BackendFactory") as mock_factory,
        patch("src.worker.main.asyncio.to_thread", new=AsyncMock(return_value=failed_report)),
    ):
        mock_factory.create.return_value = MagicMock()
        result = await orch._translate_two_phase([fake_block], fake_ctx, "", "")

    mocks["failure_interpreter"].interpret.assert_not_called()
    assert result == [fake_gb]


@pytest.mark.asyncio
async def test_translate_with_refinement_breaks_when_interpreter_fails() -> None:
    """When FailureInterpreterAgent raises, loop breaks gracefully."""
    orch, mocks = _make_orchestrator_with_mocks()
    fake_block = _make_fake_block()
    fake_gb = _make_fake_generated_block()
    fake_ctx = _make_fake_context()
    failed_report = _make_fake_report(passed=False, diff_summary="diff here")

    translator_mock = MagicMock()
    translator_mock.translate = AsyncMock(return_value=fake_gb)
    mocks["router"].route.return_value = translator_mock
    mocks["codegen"].assemble.return_value = "code"
    mocks["failure_interpreter"].interpret = AsyncMock(side_effect=RuntimeError("interpreter down"))

    with (
        patch("src.worker.main.BackendFactory") as mock_factory,
        patch("src.worker.main.asyncio.to_thread", new=AsyncMock(return_value=failed_report)),
    ):
        mock_factory.create.return_value = MagicMock()
        result = await orch._translate_two_phase([fake_block], fake_ctx, "", "")

    assert result == [fake_gb]


# ── JobOrchestrator._retry_affected_block() ───────────────────────────────────


@pytest.mark.asyncio
async def test_retry_affected_block_replaces_matching_block() -> None:
    """When block_id matches, the block is re-translated and replaced."""
    orch, mocks = _make_orchestrator_with_mocks()
    fake_block = _make_fake_block(source_file="test.sas", start_line=5)
    old_gb = _make_fake_generated_block()
    new_gb = _make_fake_generated_block()
    fake_ctx = _make_fake_context()

    translator_mock = MagicMock()
    translator_mock.translate = AsyncMock(return_value=new_gb)
    mocks["router"].route.return_value = translator_mock

    result = await orch._retry_affected_block(
        [fake_block], [old_gb], fake_ctx, "test.sas:5", "fix hint"
    )

    assert result[0] is new_gb


@pytest.mark.asyncio
async def test_retry_affected_block_no_match_returns_unchanged() -> None:
    """When no block matches the affected_id, original list is returned unchanged."""
    orch, mocks = _make_orchestrator_with_mocks()
    fake_block = _make_fake_block(source_file="test.sas", start_line=1)
    old_gb = _make_fake_generated_block()
    fake_ctx = _make_fake_context()

    result = await orch._retry_affected_block(
        [fake_block], [old_gb], fake_ctx, "other.sas:99", "fix hint"
    )

    assert result == [old_gb]
    mocks["router"].route.assert_not_called()


@pytest.mark.asyncio
async def test_retry_affected_block_swallows_translator_error() -> None:
    """Translation error during retry is swallowed and original block is kept."""
    orch, mocks = _make_orchestrator_with_mocks()
    fake_block = _make_fake_block(source_file="test.sas", start_line=3)
    old_gb = _make_fake_generated_block()
    fake_ctx = _make_fake_context()

    translator_mock = MagicMock()
    translator_mock.translate = AsyncMock(side_effect=RuntimeError("translate failed"))
    mocks["router"].route.return_value = translator_mock

    result = await orch._retry_affected_block(
        [fake_block], [old_gb], fake_ctx, "test.sas:3", "fix hint"
    )

    assert result[0] is old_gb


# ── _make_session_factory ─────────────────────────────────────────────────────


def test_make_session_factory_returns_session_maker() -> None:
    """_make_session_factory should return an async_sessionmaker without raising."""
    with patch("src.worker.main.create_async_engine") as mock_engine:
        mock_engine.return_value = MagicMock()
        from src.worker.main import _make_session_factory

        factory = _make_session_factory()
    assert factory is not None


# ── JobOrchestrator.run() — non-429 HTTPStatusError ──────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_run_reraises_non_429_http_error() -> None:
    """HTTP errors with status != 429 should be re-raised."""
    orch, _ = _make_orchestrator_with_mocks()
    session = AsyncMock()
    job = _make_job()

    response_mock = MagicMock()
    response_mock.status_code = 500
    http_err = httpx.HTTPStatusError("500", request=MagicMock(), response=response_mock)
    orch._execute = AsyncMock(side_effect=http_err)  # type: ignore[method-assign]

    with pytest.raises(httpx.HTTPStatusError):
        await orch.run(session, job)


# ── JobOrchestrator._execute() — macro expansion warning branch ───────────────


@pytest.mark.asyncio
async def test_orchestrator_execute_with_macro_expansion_warning() -> None:
    """CannotExpandError during macro expansion should be warned and job still completes."""
    from src.worker.engine.macro_expander import CannotExpandError

    orch, mocks = _make_orchestrator_with_mocks()
    session = AsyncMock()
    job = _make_job(files={"test.sas": "DATA out; SET in; RUN;"})

    fake_block = _make_fake_block()
    fake_gb = _make_fake_generated_block()
    fake_ctx = _make_fake_context()
    fake_report = _make_fake_report(passed=True)

    parse_result = MagicMock()
    parse_result.blocks = [fake_block]
    parse_result.macro_vars = []

    # expander raises CannotExpandError → warning appended
    mocks["expander"].expand.side_effect = CannotExpandError("x", "unknown macro &x")
    mocks["analysis"].analyse = AsyncMock(return_value=fake_ctx)

    translator_mock = MagicMock()
    translator_mock.translate = AsyncMock(return_value=fake_gb)
    mocks["router"].route.return_value = translator_mock
    mocks["codegen"].assemble.return_value = "code"
    mocks["doc_agent"].generate = AsyncMock(return_value=None)

    with (
        patch("src.worker.main.SASParser") as mock_parser,
        patch("src.worker.main.BackendFactory") as mock_factory,
        patch("src.worker.main.asyncio.to_thread", new=AsyncMock(return_value=fake_report)),
        patch("src.worker.main.extract_lineage", return_value=None),
    ):
        mock_parser.return_value.parse.return_value = parse_result
        mock_factory.create.return_value = MagicMock()

        await orch._execute(session, job)

    session.execute.assert_called_once()
    assert session.commit.call_count == 2


# ── _translate_two_phase — dict raw_report branch ────────────────────────────


@pytest.mark.asyncio
async def test_translate_with_refinement_dict_report_passed() -> None:
    """When raw_report is a dict with all passing checks, loop breaks immediately."""
    orch, mocks = _make_orchestrator_with_mocks()
    fake_block = _make_fake_block()
    fake_gb = _make_fake_generated_block()
    fake_ctx = _make_fake_context()

    dict_report = {"checks": [{"name": "row_count", "status": "pass"}]}

    translator_mock = MagicMock()
    translator_mock.translate = AsyncMock(return_value=fake_gb)
    mocks["router"].route.return_value = translator_mock
    mocks["codegen"].assemble.return_value = "code"

    with (
        patch("src.worker.main.BackendFactory") as mock_factory,
        patch("src.worker.main.asyncio.to_thread", new=AsyncMock(return_value=dict_report)),
    ):
        mock_factory.create.return_value = MagicMock()
        result = await orch._translate_two_phase([fake_block], fake_ctx, "", "")

    assert result == [fake_gb]
    mocks["failure_interpreter"].interpret.assert_not_called()


# ── _dict_to_recon_report ─────────────────────────────────────────────────────


def test_dict_to_recon_report_empty_checks_returns_passed() -> None:
    report = _dict_to_recon_report({"checks": []})
    assert report.passed is True
    assert report.diff_summary == "no checks run"


def test_dict_to_recon_report_all_pass() -> None:
    report = _dict_to_recon_report(
        {
            "checks": [
                {"name": "row_count", "status": "pass"},
                {"name": "columns", "status": "pass"},
            ]
        }
    )
    assert report.passed is True
    assert report.row_count_match is True
    assert report.column_match is True


def test_dict_to_recon_report_with_failures_and_details() -> None:
    report = _dict_to_recon_report(
        {
            "checks": [
                {"name": "row_count", "status": "fail", "detail": "expected 10 got 9"},
                {"name": "columns", "status": "pass"},
            ]
        }
    )
    assert report.passed is False
    assert report.row_count_match is False
    assert report.column_match is True
    assert "expected 10 got 9" in report.diff_summary


def test_dict_to_recon_report_failed_no_detail() -> None:
    report = _dict_to_recon_report({"checks": [{"name": "row_count", "status": "fail"}]})
    assert report.passed is False
    # diff_summary falls back to "N/M checks passed"
    assert "0/1" in report.diff_summary


# ── _process_job — LLMTranslationError branch ────────────────────────────────


@pytest.mark.asyncio
async def test_process_job_llm_translation_error_sets_failed() -> None:
    """LLMTranslationError mid-block sets job to failed with error_detail."""
    from src.worker.engine.llm_client import LLMTranslationError

    fake_job = _make_job()
    session = AsyncMock()

    with (
        patch("src.worker.main.SASParser") as mock_parser,
        patch("src.worker.main.extract_lineage", return_value=None),
        patch("src.worker.main.LLMClient"),
        patch("src.worker.main.CodeGenerator"),
        patch("src.worker.main.ReconciliationService"),
        patch("src.worker.main.BackendFactory"),
        patch("src.worker.main.asyncio.to_thread") as mock_thread,
    ):
        fake_block = MagicMock()
        mock_parser.return_value.parse.return_value = MagicMock(blocks=[fake_block], macro_vars={})
        err = LLMTranslationError("model overloaded", is_transient=True)
        mock_thread.side_effect = err

        await _process_job(session, fake_job)

    assert session.execute.call_count == 1
    session.commit.assert_called_once()


# ── JobOrchestrator._execute_rereconcile() ────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_rereconcile_sets_proposed_on_success() -> None:
    """skip_llm path: runs reconciliation only, sets status=proposed."""
    orch, _ = _make_orchestrator_with_mocks()
    session = AsyncMock()
    job = _make_job(python_code="result = df.copy()", skip_llm=True)
    fake_report = {"checks": [{"name": "row_count", "status": "pass"}]}

    with (
        patch("src.worker.main.BackendFactory") as mock_factory,
        patch("src.worker.main.asyncio.to_thread", new=AsyncMock(return_value=fake_report)),
    ):
        mock_factory.create.return_value = MagicMock()
        await orch._execute_rereconcile(job, session, "", "")

    session.execute.assert_called_once()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_execute_rereconcile_sets_failed_on_exception() -> None:
    """skip_llm path: exception sets status=failed and re-raises."""
    orch, _ = _make_orchestrator_with_mocks()
    session = AsyncMock()
    job = _make_job(python_code="result = df.copy()", skip_llm=True)

    with (
        patch("src.worker.main.BackendFactory") as mock_factory,
        patch(
            "src.worker.main.asyncio.to_thread",
            new=AsyncMock(side_effect=RuntimeError("recon boom")),
        ),
    ):
        mock_factory.create.return_value = MagicMock()
        with pytest.raises(RuntimeError, match="recon boom"):
            await orch._execute_rereconcile(job, session, "", "")

    assert session.execute.call_count == 1
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_execute_skips_llm_when_skip_llm_true() -> None:
    """When job.skip_llm=True, _execute calls _execute_rereconcile and returns early."""
    orch, _ = _make_orchestrator_with_mocks()
    orch._execute_rereconcile = AsyncMock()  # type: ignore[method-assign]
    session = AsyncMock()
    job = _make_job(
        files={"test.sas": "data out; set in; run;"},
        python_code="result = df.copy()",
        skip_llm=True,
    )

    await orch._execute(session, job)

    orch._execute_rereconcile.assert_called_once()
