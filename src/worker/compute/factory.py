"""BackendFactory — resolves ComputeBackend from the CLOUD environment variable."""

from src.worker.compute.base import ComputeBackend
from src.worker.compute.local import LocalBackend
from src.worker.core.config import worker_settings


class BackendFactory:
    """Creates the appropriate ComputeBackend for the current environment."""

    @staticmethod
    def create() -> ComputeBackend:
        """Return a ComputeBackend instance based on the CLOUD setting.

        Returns:
            LocalBackend when CLOUD=false.

        Raises:
            NotImplementedError: When CLOUD=true (DatabricksBackend deferred to Phase 4).
        """
        if worker_settings.cloud:
            raise NotImplementedError(
                "DatabricksBackend is not yet implemented. Set CLOUD=false to use LocalBackend."
            )
        return LocalBackend()
