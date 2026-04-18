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
    ):
        mock_parser.return_value.parse.return_value = fake_blocks
        mock_client.return_value.translate.return_value = fake_generated[0]
        mock_codegen.return_value.assemble.return_value = fake_code
        mock_factory.create.return_value = MagicMock()

        # to_thread is called twice: once for translate loop, once for reconcile
        mock_to_thread.side_effect = [fake_generated, fake_report]

        await _process_job(session, fake_job)

    # Success path: execute called once (UPDATE to done), commit called once
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
