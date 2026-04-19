"""Backend application settings loaded from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings resolved from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    database_url: str = "postgresql+asyncpg://rosetta:rosetta@localhost:5432/rosetta"
    llm_model: str = "anthropic:claude-sonnet-4-6"
    cloud: bool = False
    log_level: str = "INFO"
    upload_dir: str = "/tmp/rosetta-uploads"
    max_zip_bytes: int = 524_288_000
    cors_origins_raw: str = Field(default="*", alias="CORS_ORIGINS")

    @property
    def cors_origins(self) -> list[str]:
        """Return CORS origins as a list, split from the comma-separated raw value."""
        return [o.strip() for o in self.cors_origins_raw.split(",")]


settings = Settings()
backend_settings = settings
