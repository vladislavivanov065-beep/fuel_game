from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Gas Station Wars"
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://gaswars:gaswars@localhost:5432/gaswars"

    cors_origins: list[str] = ["http://localhost:5173"]

    session_cookie_name: str = "session_id"
    session_ttl_seconds: int = 60 * 60 * 24 * 7
    session_cookie_secure: bool = False

    auth_rate_limit_max_attempts: int = 5
    auth_rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
