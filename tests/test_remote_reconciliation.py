"""Unit tests for RemoteReconciliationService in reconciliation.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from src.worker.compute.local import LocalBackend
from src.worker.validation.reconciliation import RemoteReconciliationService


@pytest.mark.asyncio
async def test_remote_recon_returns_checks_on_success() -> None:
    """A successful executor response surfaces its checks list."""
    fake_payload = {
        "stdout": "",
        "stderr": "",
        "result_json": [{"x": 1}],
        "result_columns": ["x"],
        "checks": [{"name": "row_count", "status": "pass"}],
        "error": None,
        "elapsed_ms": 10,
    }
    fake_response = MagicMock()
    fake_response.json.return_value = fake_payload
    fake_response.raise_for_status = MagicMock()

    with patch.object(
        RemoteReconciliationService,
        "_post_execute",
        return_value=fake_payload,
    ):
        svc = RemoteReconciliationService()
        result = await svc.run(
            ref_csv_path="/tmp/ref.csv",
            python_code="x = 1",
            backend=LocalBackend(),
        )
    assert result == {"checks": [{"name": "row_count", "status": "pass"}]}


@pytest.mark.asyncio
async def test_remote_recon_returns_empty_when_no_ref() -> None:
    """No reference paths → empty checks without hitting the network."""
    svc = RemoteReconciliationService()
    result = await svc.run(
        ref_csv_path="",
        python_code="x = 1",
        backend=LocalBackend(),
        ref_sas7bdat_path="",
    )
    assert result == {"checks": []}


@pytest.mark.asyncio
async def test_remote_recon_falls_back_on_connect_error() -> None:
    """ConnectError is swallowed and returns empty checks."""
    with patch.object(
        RemoteReconciliationService,
        "_post_execute",
        side_effect=httpx.ConnectError("refused"),
    ):
        svc = RemoteReconciliationService()
        result = await svc.run(
            ref_csv_path="/tmp/ref.csv",
            python_code="x = 1",
            backend=LocalBackend(),
        )
    assert result == {"checks": []}


@pytest.mark.asyncio
async def test_remote_recon_falls_back_on_timeout() -> None:
    """TimeoutException is swallowed and returns empty checks."""
    with patch.object(
        RemoteReconciliationService,
        "_post_execute",
        side_effect=httpx.TimeoutException("timeout"),
    ):
        svc = RemoteReconciliationService()
        result = await svc.run(
            ref_csv_path="/tmp/ref.csv",
            python_code="x = 1",
            backend=LocalBackend(),
        )
    assert result == {"checks": []}


def test_post_execute_sends_request_and_returns_json() -> None:
    """_post_execute posts to executor URL and returns the parsed JSON body."""
    from unittest.mock import MagicMock, patch

    fake_body = {"checks": [{"name": "row_count", "status": "pass"}]}
    fake_response = MagicMock()
    fake_response.json.return_value = fake_body
    fake_response.raise_for_status = MagicMock()

    mock_client_instance = MagicMock()
    mock_client_instance.post.return_value = fake_response
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = MagicMock(return_value=False)

    target = "src.worker.validation.reconciliation.httpx.Client"
    with patch(target, return_value=mock_client_instance):
        svc = RemoteReconciliationService()
        result = svc._post_execute("x = 1", "/tmp/ref.csv", "")

    assert result == fake_body
    mock_client_instance.post.assert_called_once()


@pytest.mark.asyncio
async def test_remote_recon_falls_back_on_unexpected_error() -> None:
    """Unexpected exceptions are swallowed and return empty checks."""
    with patch.object(
        RemoteReconciliationService,
        "_post_execute",
        side_effect=ValueError("unexpected"),
    ):
        svc = RemoteReconciliationService()
        result = await svc.run(
            ref_csv_path="/tmp/ref.csv",
            python_code="x = 1",
            backend=LocalBackend(),
        )
    assert result == {"checks": []}
