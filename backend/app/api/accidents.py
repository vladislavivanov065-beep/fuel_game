import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_current_user
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.road_accident import RoadAccidentResponse
from app.services import accident_service

router = APIRouter(prefix="/api/games/{game_id}/accidents", tags=["accidents"])


@router.get("", response_model=list[RoadAccidentResponse])
async def list_active_accidents(
    game_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[RoadAccidentResponse]:
    try:
        accidents = await accident_service.list_active_accidents(db, game_id, user.id)
    except accident_service.GameNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found") from exc
    except accident_service.NotAGameMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        ) from exc

    return [RoadAccidentResponse.from_model(accident) for accident in accidents]
