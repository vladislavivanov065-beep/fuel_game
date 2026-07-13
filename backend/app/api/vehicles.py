import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_current_user
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.vehicle import VehicleResponse
from app.services import vehicle_service

router = APIRouter(prefix="/api/games/{game_id}", tags=["vehicles"])


@router.get("/vehicles", response_model=list[VehicleResponse])
async def list_vehicles(
    game_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[VehicleResponse]:
    try:
        vehicles = await vehicle_service.list_game_vehicles(db, game_id, user.id)
    except vehicle_service.GameNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found") from exc
    except vehicle_service.NotAGameMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        ) from exc

    return [VehicleResponse.from_model(vehicle) for vehicle in vehicles]
