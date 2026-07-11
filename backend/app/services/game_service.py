import secrets
import uuid
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.financial_transaction import FinancialTransaction
from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom, GameStatus
from app.schemas.game import CreateGameRequest
from app.schemas.game_settings import GameSettings
from app.services import station_service

_INVITE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_INVITE_CODE_LENGTH = 8
_MAX_INVITE_CODE_ATTEMPTS = 5


class GameNotFoundError(Exception):
    pass


class NotAGameMemberError(Exception):
    pass


class InviteCodeGenerationError(Exception):
    pass


class InvalidInviteCodeError(Exception):
    pass


class GameNotJoinableError(Exception):
    pass


class AlreadyJoinedError(Exception):
    pass


class CreatorCannotLeaveError(Exception):
    pass


class NotGameCreatorError(Exception):
    pass


class GameAlreadyStartedError(Exception):
    pass


class NetworkNameTakenError(Exception):
    pass


def _generate_invite_code() -> str:
    return "".join(secrets.choice(_INVITE_CODE_ALPHABET) for _ in range(_INVITE_CODE_LENGTH))


async def create_game(db: AsyncSession, creator_id: uuid.UUID, data: CreateGameRequest) -> GameRoom:
    settings_payload = data.settings.model_dump(mode="json")

    for _ in range(_MAX_INVITE_CODE_ATTEMPTS):
        game = GameRoom(
            name=data.name,
            invite_code=_generate_invite_code(),
            creator_id=creator_id,
            settings_json=settings_payload,
        )
        db.add(game)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            continue

        db.add(GamePlayer(game_id=game.id, user_id=creator_id, is_admin=True))
        await db.commit()

        return await get_game_for_member(db, game.id, creator_id)

    raise InviteCodeGenerationError


async def get_game_for_member(db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID) -> GameRoom:
    stmt = (
        select(GameRoom)
        .where(GameRoom.id == game_id)
        .options(selectinload(GameRoom.players).selectinload(GamePlayer.user))
    )
    game = (await db.execute(stmt)).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError

    if not any(player.user_id == user_id for player in game.players):
        raise NotAGameMemberError

    return game


async def list_games_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[GameRoom]:
    member_game_ids = select(GamePlayer.game_id).where(GamePlayer.user_id == user_id)

    stmt = (
        select(GameRoom)
        .where(GameRoom.id.in_(member_game_ids))
        .options(selectinload(GameRoom.players))
        .order_by(GameRoom.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().unique())


async def resolve_by_invite_code(db: AsyncSession, invite_code: str) -> GameRoom:
    stmt = (
        select(GameRoom)
        .where(GameRoom.invite_code == invite_code)
        .options(selectinload(GameRoom.players))
    )
    game = (await db.execute(stmt)).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError

    return game


async def join_game(
    db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID, invite_code: str
) -> GameRoom:
    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError

    if not secrets.compare_digest(game.invite_code, invite_code):
        raise InvalidInviteCodeError

    room_settings = GameSettings.model_validate(game.settings_json)
    joinable = game.status == GameStatus.LOBBY or (
        game.status == GameStatus.RUNNING and room_settings.allow_join_after_start
    )
    if not joinable:
        raise GameNotJoinableError

    db.add(GamePlayer(game_id=game.id, user_id=user_id))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AlreadyJoinedError from exc

    return await get_game_for_member(db, game.id, user_id)


async def leave_game(db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID) -> None:
    stmt = select(GamePlayer).where(GamePlayer.game_id == game_id, GamePlayer.user_id == user_id)
    player = (await db.execute(stmt)).scalar_one_or_none()
    if player is None:
        raise NotAGameMemberError

    if player.is_admin:
        raise CreatorCannotLeaveError

    await db.delete(player)
    await db.commit()


async def set_ready(
    db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID, is_ready: bool
) -> GamePlayer:
    stmt = select(GamePlayer).where(GamePlayer.game_id == game_id, GamePlayer.user_id == user_id)
    player = (await db.execute(stmt)).scalar_one_or_none()
    if player is None:
        raise NotAGameMemberError

    player.is_ready = is_ready
    await db.commit()
    await db.refresh(player)
    return player


async def set_network(
    db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID, network_name: str, network_color: str
) -> GamePlayer:
    stmt = select(GamePlayer).where(GamePlayer.game_id == game_id, GamePlayer.user_id == user_id)
    player = (await db.execute(stmt)).scalar_one_or_none()
    if player is None:
        raise NotAGameMemberError

    player.network_name = network_name
    player.network_color = network_color
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise NetworkNameTakenError from exc

    await db.refresh(player)
    return player


async def get_network(db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID) -> GamePlayer:
    stmt = select(GamePlayer).where(GamePlayer.game_id == game_id, GamePlayer.user_id == user_id)
    player = (await db.execute(stmt)).scalar_one_or_none()
    if player is None:
        raise NotAGameMemberError
    return player


async def list_my_transactions(
    db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID
) -> list[FinancialTransaction]:
    player = await get_network(db, game_id, user_id)

    stmt = (
        select(FinancialTransaction)
        .where(FinancialTransaction.player_id == player.id)
        .order_by(FinancialTransaction.created_at)
    )
    return list((await db.execute(stmt)).scalars().all())


async def start_game(db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID) -> GameRoom:
    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError

    if game.creator_id != user_id:
        raise NotGameCreatorError

    result = cast(
        CursorResult[Any],
        await db.execute(
            update(GameRoom)
            .where(GameRoom.id == game_id, GameRoom.status == GameStatus.LOBBY)
            .values(status=GameStatus.RUNNING, started_at=func.now())
        ),
    )
    if result.rowcount != 1:
        await db.rollback()
        raise GameAlreadyStartedError

    room_settings = GameSettings.model_validate(game.settings_json)
    await db.execute(
        update(GamePlayer)
        .where(GamePlayer.game_id == game_id)
        .values(balance=room_settings.starting_balance)
    )
    await station_service.create_game_stations_for_game(db, game_id, room_settings)
    await db.commit()

    return await get_game_for_member(db, game_id, user_id)
