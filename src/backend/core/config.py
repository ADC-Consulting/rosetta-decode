"""Backend application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings resolved from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://rosetta:rosetta@localhost:5432/rosetta"
    llm_model: str = "anthropic:claude-sonnet-4-6"
    cloud: bool = False
    log_level: str = "INFO"


settings = Settings()
