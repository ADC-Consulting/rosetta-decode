"""Unit tests for src/worker/core/config.py — WorkerSettings validation.

Covers the startup-time CLOUD=true guard added for GitHub issue #140.
"""

import pytest
from pydantic import ValidationError
from src.worker.core.config import WorkerSettings


def test_worker_settings_constructs_with_cloud_false() -> None:
    settings = WorkerSettings(cloud=False)

    assert settings.cloud is False


def test_worker_settings_constructs_with_cloud_unset() -> None:
    settings = WorkerSettings()

    assert settings.cloud is False


def test_worker_settings_rejects_cloud_true() -> None:
    with pytest.raises(ValidationError) as exc_info:
        WorkerSettings(cloud=True)

    message = str(exc_info.value)
    assert "DatabricksBackend is not yet implemented" in message
    assert "Set CLOUD=false to use LocalBackend" in message
