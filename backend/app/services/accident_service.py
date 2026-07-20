import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.road_accident import RoadAccident
from app.services import game_service
from app.services.game_service import GameNotFoundError, NotAGameMemberError

__all__ = ["GameNotFoundError", "NotAGameMemberError", "list_active_accidents"]


async def list_active_accidents(
    db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID
) -> list[RoadAccident]:
    await game_service.get_game_for_member(db, game_id, user_id)

    accidents = (
        (
            await db.execute(
                select(RoadAccident).where(
                    RoadAccident.game_id == game_id, RoadAccident.ends_at > datetime.now(UTC)
                )
            )
        )
        .scalars()
        .all()
    )
    return list(accidents)
