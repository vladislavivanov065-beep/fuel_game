from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client
from app.schemas.health import HealthResponse


async def check_health(db: AsyncSession) -> HealthResponse:
    database_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        database_status = "unavailable"

    redis_status = "ok"
    try:
        await redis_client.ping()
    except Exception:
        redis_status = "unavailable"

    overall = "ok" if database_status == "ok" and redis_status == "ok" else "degraded"
    return HealthResponse(status=overall, database=database_status, redis=redis_status)
