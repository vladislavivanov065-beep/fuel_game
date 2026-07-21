import json
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Gas Station Wars"
    environment: str = "development"
    log_level: str = "INFO"

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

    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        # Accept either a JSON array (`["https://a", "https://b"]`) or a plain
        # comma-separated string (`https://a,https://b`) — deployment UIs
        # (Railway, ...) invite typing a bare value with no JSON syntax.
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value

    session_cookie_name: str = "session_id"
    session_ttl_seconds: int = 60 * 60 * 24 * 7
    session_cookie_secure: bool = False

    auth_rate_limit_max_attempts: int = 5
    auth_rate_limit_window_seconds: int = 60

    password_reset_ttl_seconds: int = 60 * 15

    # Защита от зависших блокировок в Postgres (например, если предыдущий
    # инстанс был убит платформой посреди транзакции и не успел её закрыть):
    # без этих таймаутов ждущий блокировку запрос висит бесконечно и не
    # даёт стартовать ни одному следующему деплою, пока кто-то вручную не
    # перезапустит саму БД.
    db_statement_timeout_ms: int = 30_000
    db_lock_timeout_ms: int = 10_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
