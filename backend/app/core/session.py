import secrets
import uuid

from app.core.config import get_settings
from app.core.redis import redis_client

settings = get_settings()

_SESSION_KEY_PREFIX = "session:"


def _session_key(token: str) -> str:
    return f"{_SESSION_KEY_PREFIX}{token}"


async def create_session(user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    await redis_client.set(_session_key(token), str(user_id), ex=settings.session_ttl_seconds)
    return token


async def get_session_user_id(token: str) -> uuid.UUID | None:
    raw_user_id = await redis_client.get(_session_key(token))
    if raw_user_id is None:
        return None
    if isinstance(raw_user_id, bytes):
        raw_user_id = raw_user_id.decode()
    return uuid.UUID(raw_user_id)


async def delete_session(token: str) -> None:
    await redis_client.delete(_session_key(token))
