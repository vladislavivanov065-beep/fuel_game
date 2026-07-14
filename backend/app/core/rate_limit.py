import time

from fastapi import HTTPException, Request, status

from app.core.config import get_settings

settings = get_settings()

_attempts: dict[str, tuple[int, float]] = {}


def reset_rate_limits() -> None:
    _attempts.clear()


class AuthRateLimiter:
    def __init__(self, scope: str) -> None:
        self._scope = scope

    async def __call__(self, request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"{self._scope}:{client_ip}"
        now = time.monotonic()

        count, reset_at = _attempts.get(key, (0, now))
        if now >= reset_at:
            count, reset_at = 0, now + settings.auth_rate_limit_window_seconds

        count += 1
        _attempts[key] = (count, reset_at)

        if count > settings.auth_rate_limit_max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts, please try again later.",
            )
