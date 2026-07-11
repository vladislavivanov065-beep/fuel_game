from fastapi import HTTPException, Request, status

from app.core.config import get_settings
from app.core.redis import redis_client

settings = get_settings()


class AuthRateLimiter:
    def __init__(self, scope: str) -> None:
        self._scope = scope

    async def __call__(self, request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"rate_limit:{self._scope}:{client_ip}"

        attempts = await redis_client.incr(key)
        if attempts == 1:
            await redis_client.expire(key, settings.auth_rate_limit_window_seconds)

        if attempts > settings.auth_rate_limit_max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts, please try again later.",
            )
