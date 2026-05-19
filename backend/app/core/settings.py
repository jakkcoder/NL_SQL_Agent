from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or backend/.env."""

    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    default_dev_arn: str = Field(default="ARN-0411", alias="DEFAULT_DEV_ARN")
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    google_adk_model: str = Field(default="gemini-2.0-flash", alias="GOOGLE_ADK_MODEL")
    db_statement_timeout_ms: int = Field(default=15000, alias="DB_STATEMENT_TIMEOUT_MS")
    default_page_limit: int = Field(default=25, alias="DEFAULT_PAGE_LIMIT")
    max_intersection_rows: int = Field(default=5000, alias="MAX_INTERSECTION_ROWS")
    allowed_origins: str = Field(
        default="http://localhost:8000,http://localhost:3000,http://127.0.0.1:5500,null",
        alias="ALLOWED_ORIGINS",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
