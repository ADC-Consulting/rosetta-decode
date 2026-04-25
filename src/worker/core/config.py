"""Worker service settings loaded from environment variables."""

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


worker_settings = WorkerSettings()
