"""Unit tests for BackendFactory."""

from unittest.mock import patch

import pytest
from src.worker.compute.factory import BackendFactory
from src.worker.compute.local import LocalBackend


def test_factory_returns_local_backend_when_cloud_false() -> None:
    with patch("src.worker.compute.factory.worker_settings") as mock_settings:
        mock_settings.cloud = False
        backend = BackendFactory.create()
    assert isinstance(backend, LocalBackend)


def test_factory_raises_when_cloud_true() -> None:
    with patch("src.worker.compute.factory.worker_settings") as mock_settings:
        mock_settings.cloud = True
        with pytest.raises(NotImplementedError, match="DatabricksBackend"):
            BackendFactory.create()
