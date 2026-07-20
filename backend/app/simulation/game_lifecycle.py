import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom, GameStatus
from app.db.models.game_station import GameStation
from app.db.models.station_upgrade import StationUpgrade
from app.schemas.game_settings import GameSettings


def _upgrade_invested_value(base_cost: Decimal, cost_per_level: Decimal, level: int) -> Decimal:
    """Total money spent to reach ``level`` (level 1 costs base_cost, level N costs
    base_cost + cost_per_level*(N-1)); this is that cost summed over levels 1..N."""
    n = Decimal(level)
    return n * base_cost + cost_per_level * (n * (n - Decimal(1)) / Decimal(2))


async def compute_net_worth(db: AsyncSession, game_id: uuid.UUID) -> dict[uuid.UUID, Decimal]:
    """net_worth = cash + stations_market_value + fuel_inventory_value + upgrade_value - debts.

    debts is always 0 for now: this MVP has no lending/credit mechanic.
    """
    game = await db.get(GameRoom, game_id)
    if game is None:
        return {}
    settings = GameSettings.model_validate(game.settings_json)

    players = (
        (await db.execute(select(GamePlayer).where(GamePlayer.game_id == game_id))).scalars().all()
    )
    net_worth: dict[uuid.UUID, Decimal] = {player.id: player.balance for player in players}

    stations = (
        (
            await db.execute(
                select(GameStation)
                .where(GameStation.game_id == game_id, GameStation.owner_player_id.is_not(None))
                .options(selectinload(GameStation.fuels))
            )
        )
        .scalars()
        .all()
    )

    station_owner: dict[uuid.UUID, uuid.UUID] = {}
    for station in stations:
        owner_id = station.owner_player_id
        if owner_id is None or owner_id not in net_worth:
            continue
        station_owner[station.id] = owner_id
        net_worth[owner_id] += station.purchase_price
        for fuel in station.fuels:
            net_worth[owner_id] += fuel.current_liters * fuel.average_purchase_price

    if station_owner:
        upgrades = (
            (
                await db.execute(
                    select(StationUpgrade).where(
                        StationUpgrade.station_id.in_(station_owner.keys())
                    )
                )
            )
            .scalars()
            .all()
        )
        for upgrade in upgrades:
            owner_id = station_owner.get(upgrade.station_id)
            if owner_id is None:
                continue
            type_settings = settings.station_upgrades[upgrade.upgrade_type.value]
            net_worth[owner_id] += _upgrade_invested_value(
                type_settings.base_cost, type_settings.cost_per_level, upgrade.level
            )

    return net_worth


async def maybe_finish_game(db: AsyncSession, game: GameRoom) -> dict[uuid.UUID, Decimal] | None:
    """If the game's time-based duration has elapsed, compute+persist net worth and
    atomically transition RUNNING -> FINISHED. Returns the net worth map if this call
    is the one that finished the game, otherwise None (not due yet, or already finished
    by a concurrent tick)."""
    if game.started_at is None:
        return None

    settings = GameSettings.model_validate(game.settings_json)
    elapsed_minutes = (datetime.now(UTC) - game.started_at).total_seconds() / 60
    if elapsed_minutes < settings.duration_minutes:
        return None

    net_worth = await compute_net_worth(db, game.id)

    finish_result = cast(
        CursorResult[Any],
        await db.execute(
            update(GameRoom)
            .where(GameRoom.id == game.id, GameRoom.status == GameStatus.RUNNING)
            .values(status=GameStatus.FINISHED, finished_at=datetime.now(UTC))
        ),
    )
    if finish_result.rowcount != 1:
        await db.rollback()
        return None

    for player_id, value in net_worth.items():
        await db.execute(
            update(GamePlayer).where(GamePlayer.id == player_id).values(net_worth=value)
        )

    await db.commit()
    return net_worth
