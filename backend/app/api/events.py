import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_current_user
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.game_event import GameEventResponse, TriggerEventRequest
from app.services import event_service, game_service
from app.websocket.connection_manager import connection_manager

router = APIRouter(prefix="/api/games/{game_id}/events", tags=["events"])


async def _ensure_game_member(db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID) -> None:
    try:
        await game_service.get_game_for_member(db, game_id, user_id)
    except game_service.GameNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found") from exc
    except game_service.NotAGameMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        ) from exc


@router.get("", response_model=list[GameEventResponse])
async def list_active_events(
    game_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[GameEventResponse]:
    await _ensure_game_member(db, game_id, user.id)

    events = await event_service.list_active_events(db, game_id)
    return [GameEventResponse.from_model(event) for event in events]


@router.get("/history", response_model=list[GameEventResponse])
async def list_event_history(
    game_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[GameEventResponse]:
    await _ensure_game_member(db, game_id, user.id)

    events = await event_service.list_event_history(db, game_id)
    return [GameEventResponse.from_model(event) for event in events]


@router.post("", response_model=GameEventResponse, status_code=status.HTTP_201_CREATED)
async def trigger_event(
    game_id: uuid.UUID,
    data: TriggerEventRequest,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> GameEventResponse:
    try:
        event = await event_service.trigger_event(db, game_id, user.id, data.event_type)
    except event_service.GameNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found") from exc
    except event_service.GameNotRunningError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Game is not running"
        ) from exc
    except event_service.NotAGameMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        ) from exc
    except event_service.NotGameAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the room creator can trigger events",
        ) from exc

    await connection_manager.broadcast(
        game_id,
        "game_event.started",
        {
            "event_id": str(event.id),
            "event_type": event.event_type.value,
            "region": event.region_json,
            "ends_at": event.ends_at.isoformat(),
        },
    )

    return GameEventResponse.from_model(event)
