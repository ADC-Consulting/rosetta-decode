"""Unit tests for src/worker/main.py — mocks DB session and engine components."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.backend.db.models import Job
from src.worker.main import _claim_job, _process_job


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
