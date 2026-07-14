from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Gas Station Wars"
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://gaswars:gaswars@localhost:5432/gaswars"

    @field_validator("database_url")
    @classmethod
    def _require_asyncpg_driver(cls, value: str) -> str:
        # Managed Postgres providers (Railway, Heroku, ...) hand out a bare
        # postgres(ql):// URL with no driver, which SQLAlchemy resolves to
        # the sync psycopg2 dialect. Force the asyncpg driver we actually need.
        if value.startswith("postgres://"):
            return "postgresql+asyncpg://" + value.removeprefix("postgres://")
        if value.startswith("postgresql://"):
            return "postgresql+asyncpg://" + value.removeprefix("postgresql://")
        return value

    cors_origins: list[str] = ["http://localhost:5173"]

    session_cookie_name: str = "session_id"
    session_ttl_seconds: int = 60 * 60 * 24 * 7
    session_cookie_secure: bool = False

    auth_rate_limit_max_attempts: int = 5
    auth_rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
