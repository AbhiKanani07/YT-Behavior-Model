from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/youtube_recs",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"], alias="CORS_ORIGINS")
    youtube_api_key: str | None = Field(default=None, alias="YOUTUBE_API_KEY")
    enable_takeout_import: bool = Field(default=True, alias="ENABLE_TAKEOUT_IMPORT")

    recommendation_cache_ttl_seconds: int = 1800
    api_cache_ttl_seconds: int = 300

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if value is None:
            return ["*"]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raw = str(value).strip()
        if not raw:
            return ["*"]
        if raw.startswith("[") and raw.endswith("]"):
            raw = raw[1:-1]
        return [part.strip().strip("'\"") for part in raw.split(",") if part.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
