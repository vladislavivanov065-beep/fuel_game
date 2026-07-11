import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_current_user
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.station import GameStationResponse
from app.services import game_service, station_service
from app.websocket.connection_manager import connection_manager

router = APIRouter(prefix="/api/games/{game_id}/stations", tags=["stations"])


async def _ensure_game_member(db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID) -> None:
    try:
        await game_service.get_game_for_member(db, game_id, user_id)
    except game_service.GameNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found") from exc
    except game_service.NotAGameMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        ) from exc


@router.get("", response_model=list[GameStationResponse])
async def list_stations(
    game_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[GameStationResponse]:
    await _ensure_game_member(db, game_id, user.id)

    stations = await station_service.list_game_stations(db, game_id)
    return [GameStationResponse.from_model(s) for s in stations]


@router.get("/{station_id}", response_model=GameStationResponse)
async def get_station(
    game_id: uuid.UUID,
    station_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> GameStationResponse:
    await _ensure_game_member(db, game_id, user.id)

    try:
        station = await station_service.get_game_station(db, game_id, station_id)
    except station_service.StationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Station not found"
        ) from exc

    return GameStationResponse.from_model(station)


@router.post("/{station_id}/purchase", response_model=GameStationResponse)
async def purchase_station(
    game_id: uuid.UUID,
    station_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> GameStationResponse:
    try:
        station = await station_service.purchase_station(db, game_id, station_id, user.id)
    except station_service.GameNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found") from exc
    except station_service.GameNotRunningError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Game is not running"
        ) from exc
    except station_service.NotAGameMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        ) from exc
    except station_service.StationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Station not found"
        ) from exc
    except station_service.StationAlreadyOwnedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This station is already owned"
        ) from exc
    except station_service.InsufficientFundsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Insufficient funds"
        ) from exc

    await connection_manager.broadcast(
        game_id,
        "station.purchased",
        {
            "station_id": str(station.id),
            "owner_player_id": str(station.owner_player_id),
            "owner_display_name": station.owner.user.display_name if station.owner else None,
            "owner_network_color": station.owner.network_color if station.owner else None,
            "purchase_price": str(station.purchase_price),
        },
    )

    return GameStationResponse.from_model(station)
