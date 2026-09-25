"""Worker service settings loaded from environment variables."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    """Settings for the async worker service."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://rosetta:rosetta@localhost:5432/rosetta"
    llm_model: str = "anthropic:claude-sonnet-4-6"
    cloud: bool = False
    poll_interval_seconds: int = 5
    log_level: str = "INFO"

    # Azure OpenAI — set these to use Azure instead of direct OpenAI/Anthropic
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    openai_api_version: str = "2024-06-01"

    # TensorZero gateway — when set, LLM calls are routed through the gateway
    tensorzero_gateway_url: str | None = None
    executor_url: str = "http://executor:8001"
    upload_dir: str = "/uploads"

    # Fail fast at process boot instead of after a full (paid) LLM pipeline run
    # hits BackendFactory.create() — see GitHub issue #140.
    @field_validator("cloud")
    @classmethod
    def _reject_cloud_until_databricks_backend_exists(cls, v: bool) -> bool:
        """Reject CLOUD=true at startup since DatabricksBackend is not implemented.

        Args:
            v: The raw `cloud` value supplied via environment/`.env`.

        Returns:
            The validated `cloud` value (always `False`).

        Raises:
            ValueError: If `cloud` is `True`. Mirrors the runtime backstop in
                `BackendFactory.create()` so both error sites give the same message.
        """
        if v:
            raise ValueError(
                "DatabricksBackend is not yet implemented. Set CLOUD=false to use LocalBackend."
            )
        return v


worker_settings = WorkerSettings()
