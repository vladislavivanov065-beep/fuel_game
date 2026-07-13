import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.vehicle import Vehicle
from app.services import game_service
from app.services.game_service import GameNotFoundError, NotAGameMemberError

__all__ = ["GameNotFoundError", "NotAGameMemberError", "list_game_vehicles"]


async def list_game_vehicles(
    db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID
) -> list[Vehicle]:
    await game_service.get_game_for_member(db, game_id, user_id)

    vehicles = (
        (
            await db.execute(
                select(Vehicle)
                .where(Vehicle.game_id == game_id)
                .order_by(Vehicle.started_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(vehicles)
