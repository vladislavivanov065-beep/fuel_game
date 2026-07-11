import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_current_user
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.game import (
    CreateGameRequest,
    GameDetailResponse,
    GamePlayerResponse,
    GameSummaryResponse,
    InvitePreviewResponse,
    JoinGameRequest,
    SetNetworkRequest,
    SetReadyRequest,
)
from app.services import game_service
from app.websocket.connection_manager import connection_manager

router = APIRouter(prefix="/api/games", tags=["games"])


@router.post("", response_model=GameDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_game(
    data: CreateGameRequest,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> GameDetailResponse:
    try:
        game = await game_service.create_game(db, user.id, data)
    except game_service.InviteCodeGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate a unique invite code, please retry",
        ) from exc

    return GameDetailResponse.from_model(game)


@router.get("", response_model=list[GameSummaryResponse])
async def list_games(
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[GameSummaryResponse]:
    games = await game_service.list_games_for_user(db, user.id)
    return [GameSummaryResponse.from_model(game) for game in games]


@router.get("/resolve/{invite_code}", response_model=InvitePreviewResponse)
async def resolve_invite_code(
    invite_code: str,
    _user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> InvitePreviewResponse:
    try:
        game = await game_service.resolve_by_invite_code(db, invite_code)
    except game_service.GameNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invite code not found"
        ) from exc

    return InvitePreviewResponse.from_model(game)


@router.get("/{game_id}", response_model=GameDetailResponse)
async def get_game(
    game_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> GameDetailResponse:
    try:
        game = await game_service.get_game_for_member(db, game_id, user.id)
    except game_service.GameNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found") from exc
    except game_service.NotAGameMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        ) from exc

    return GameDetailResponse.from_model(game)


@router.post("/{game_id}/join", response_model=GameDetailResponse)
async def join_game(
    game_id: uuid.UUID,
    data: JoinGameRequest,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> GameDetailResponse:
    try:
        game = await game_service.join_game(db, game_id, user.id, data.invite_code)
    except game_service.GameNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found") from exc
    except game_service.InvalidInviteCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid invite code"
        ) from exc
    except game_service.GameNotJoinableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This game cannot be joined right now"
        ) from exc
    except game_service.AlreadyJoinedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="You already joined this game"
        ) from exc

    await connection_manager.broadcast(
        game_id,
        "player.joined",
        {"user_id": str(user.id), "display_name": user.display_name},
    )
    return GameDetailResponse.from_model(game)


@router.post("/{game_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_game(
    game_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    try:
        await game_service.leave_game(db, game_id, user.id)
    except game_service.NotAGameMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        ) from exc
    except game_service.CreatorCannotLeaveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="The creator cannot leave the game"
        ) from exc

    await connection_manager.broadcast(
        game_id,
        "player.left",
        {"user_id": str(user.id), "display_name": user.display_name},
    )


@router.post("/{game_id}/ready", response_model=GamePlayerResponse)
async def set_ready(
    game_id: uuid.UUID,
    data: SetReadyRequest,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> GamePlayerResponse:
    try:
        player = await game_service.set_ready(db, game_id, user.id, data.is_ready)
    except game_service.NotAGameMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        ) from exc

    await connection_manager.broadcast(
        game_id,
        "player.updated",
        {"user_id": str(user.id), "is_ready": player.is_ready},
    )
    return GamePlayerResponse(
        id=player.id,
        user_id=player.user_id,
        display_name=user.display_name,
        network_name=player.network_name,
        network_color=player.network_color,
        balance=player.balance,
        net_worth=player.net_worth,
        is_ready=player.is_ready,
        is_admin=player.is_admin,
        joined_at=player.joined_at,
    )


@router.post("/{game_id}/start", response_model=GameDetailResponse)
async def start_game(
    game_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> GameDetailResponse:
    try:
        game = await game_service.start_game(db, game_id, user.id)
    except game_service.GameNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found") from exc
    except game_service.NotGameCreatorError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only the creator can start the game"
        ) from exc
    except game_service.GameAlreadyStartedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This game has already started"
        ) from exc

    await connection_manager.broadcast(
        game_id,
        "game.started",
        {"started_at": game.started_at.isoformat() if game.started_at else None},
    )
    return GameDetailResponse.from_model(game)


async def _set_network(
    game_id: uuid.UUID,
    data: SetNetworkRequest,
    user: User,
    db: AsyncSession,
) -> GamePlayerResponse:
    try:
        player = await game_service.set_network(
            db, game_id, user.id, data.network_name, data.network_color
        )
    except game_service.NotAGameMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        ) from exc
    except game_service.NetworkNameTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This network name is already taken in this game",
        ) from exc

    await connection_manager.broadcast(
        game_id,
        "player.updated",
        {
            "user_id": str(user.id),
            "network_name": player.network_name,
            "network_color": player.network_color,
        },
    )
    return GamePlayerResponse(
        id=player.id,
        user_id=player.user_id,
        display_name=user.display_name,
        network_name=player.network_name,
        network_color=player.network_color,
        balance=player.balance,
        net_worth=player.net_worth,
        is_ready=player.is_ready,
        is_admin=player.is_admin,
        joined_at=player.joined_at,
    )


@router.post("/{game_id}/network", response_model=GamePlayerResponse)
async def create_network(
    game_id: uuid.UUID,
    data: SetNetworkRequest,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> GamePlayerResponse:
    return await _set_network(game_id, data, user, db)


@router.patch("/{game_id}/network", response_model=GamePlayerResponse)
async def update_network(
    game_id: uuid.UUID,
    data: SetNetworkRequest,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> GamePlayerResponse:
    return await _set_network(game_id, data, user, db)


@router.get("/{game_id}/network", response_model=GamePlayerResponse)
async def get_network(
    game_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> GamePlayerResponse:
    try:
        player = await game_service.get_network(db, game_id, user.id)
    except game_service.NotAGameMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        ) from exc

    return GamePlayerResponse(
        id=player.id,
        user_id=player.user_id,
        display_name=user.display_name,
        network_name=player.network_name,
        network_color=player.network_color,
        balance=player.balance,
        net_worth=player.net_worth,
        is_ready=player.is_ready,
        is_admin=player.is_admin,
        joined_at=player.joined_at,
    )
