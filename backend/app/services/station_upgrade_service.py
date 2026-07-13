import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.financial_transaction import (
    TRANSACTION_TYPE_STATION_UPGRADE,
    FinancialTransaction,
)
from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom, GameStatus
from app.db.models.game_station import GameStation
from app.db.models.station_upgrade import StationUpgrade, UpgradeStatus, UpgradeType
from app.schemas.game_settings import GameSettings, StationUpgradeTypeSettings


class GameNotFoundError(Exception):
    pass


class GameNotRunningError(Exception):
    pass


class NotAGameMemberError(Exception):
    pass


class StationNotFoundError(Exception):
    pass


class StationNotOwnedByPlayerError(Exception):
    pass


class StationLevelTooLowError(Exception):
    pass


class InsufficientFundsError(Exception):
    pass


def next_upgrade_cost(type_settings: StationUpgradeTypeSettings, current_level: int) -> Decimal:
    """Cost of the next level; ``current_level`` is 0 for a not-yet-purchased upgrade."""
    return type_settings.base_cost + type_settings.cost_per_level * current_level


async def list_station_upgrades(
    db: AsyncSession, game_id: uuid.UUID, station_id: uuid.UUID
) -> list[StationUpgrade]:
    upgrades = (
        (
            await db.execute(
                select(StationUpgrade).where(
                    StationUpgrade.game_id == game_id, StationUpgrade.station_id == station_id
                )
            )
        )
        .scalars()
        .all()
    )
    return list(upgrades)


@dataclass(frozen=True)
class UpgradeInfo:
    upgrade_type: UpgradeType
    level: int
    status: UpgradeStatus | None
    next_level_cost: Decimal
    build_minutes: float
    min_station_level: int
    completed_at: datetime | None


async def list_upgrade_info(
    db: AsyncSession, game_id: uuid.UUID, station_id: uuid.UUID
) -> list[UpgradeInfo]:
    """One entry per upgrade type (including not-yet-purchased ones), so the
    frontend can render a full upgrade panel with next-level costs."""
    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError

    room_settings = GameSettings.model_validate(game.settings_json)
    existing_by_type = {
        upgrade.upgrade_type: upgrade
        for upgrade in await list_station_upgrades(db, game_id, station_id)
    }

    infos: list[UpgradeInfo] = []
    for upgrade_type in UpgradeType:
        type_settings = room_settings.station_upgrades[upgrade_type.value]
        upgrade = existing_by_type.get(upgrade_type)
        current_level = upgrade.level if upgrade is not None else 0
        infos.append(
            UpgradeInfo(
                upgrade_type=upgrade_type,
                level=current_level,
                status=upgrade.status if upgrade is not None else None,
                next_level_cost=next_upgrade_cost(type_settings, current_level),
                build_minutes=type_settings.build_minutes,
                min_station_level=type_settings.min_station_level,
                completed_at=upgrade.completed_at if upgrade is not None else None,
            )
        )
    return infos


async def purchase_upgrade(
    db: AsyncSession,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
    station_id: uuid.UUID,
    upgrade_type: UpgradeType,
) -> StationUpgrade:
    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError
    if game.status != GameStatus.RUNNING:
        raise GameNotRunningError

    room_settings = GameSettings.model_validate(game.settings_json)
    type_settings = room_settings.station_upgrades[upgrade_type.value]

    player = (
        await db.execute(
            select(GamePlayer)
            .where(GamePlayer.game_id == game_id, GamePlayer.user_id == user_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if player is None:
        raise NotAGameMemberError

    station = (
        await db.execute(
            select(GameStation)
            .where(GameStation.id == station_id, GameStation.game_id == game_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if station is None:
        raise StationNotFoundError
    if station.owner_player_id != player.id:
        raise StationNotOwnedByPlayerError
    if station.level < type_settings.min_station_level:
        raise StationLevelTooLowError

    existing = (
        await db.execute(
            select(StationUpgrade)
            .where(
                StationUpgrade.station_id == station_id,
                StationUpgrade.upgrade_type == upgrade_type,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    current_level = existing.level if existing is not None else 0
    cost = next_upgrade_cost(type_settings, current_level)

    if player.balance < cost:
        raise InsufficientFundsError

    balance_before = player.balance
    player.balance = balance_before - cost
    balance_after = player.balance

    now = datetime.now(UTC)
    completed_at = now + timedelta(minutes=type_settings.build_minutes)

    if existing is None:
        upgrade = StationUpgrade(
            game_id=game_id,
            station_id=station_id,
            upgrade_type=upgrade_type,
            level=1,
            status=UpgradeStatus.UNDER_CONSTRUCTION,
            started_at=now,
            completed_at=completed_at,
        )
        db.add(upgrade)
    else:
        existing.level += 1
        existing.status = UpgradeStatus.UNDER_CONSTRUCTION
        existing.started_at = now
        existing.completed_at = completed_at
        upgrade = existing

    db.add(
        FinancialTransaction(
            game_id=game_id,
            player_id=player.id,
            transaction_type=TRANSACTION_TYPE_STATION_UPGRADE,
            amount=-cost,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type="station_upgrade",
            reference_id=station_id,
        )
    )

    await db.commit()
    await db.refresh(upgrade)
    return upgrade
