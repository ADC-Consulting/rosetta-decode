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


worker_settings = WorkerSettings()
