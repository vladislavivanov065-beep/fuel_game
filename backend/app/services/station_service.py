import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import CursorResult, Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.financial_transaction import (
    TRANSACTION_TYPE_STATION_PURCHASE,
    FinancialTransaction,
)
from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom, GameStatus
from app.db.models.game_station import GameStation
from app.db.models.station_fuel import FuelType, StationFuel
from app.db.models.station_template import StationTemplate
from app.schemas.game_settings import GameSettings

_DEFAULT_RETAIL_PRICES: dict[FuelType, Decimal] = {
    FuelType.AI92: Decimal("55.00"),
    FuelType.AI95: Decimal("58.00"),
    FuelType.DIESEL: Decimal("60.00"),
}


class GameNotFoundError(Exception):
    pass


class NotAGameMemberError(Exception):
    pass


class GameNotRunningError(Exception):
    pass


class StationNotFoundError(Exception):
    pass


class StationAlreadyOwnedError(Exception):
    pass


class InsufficientFundsError(Exception):
    pass


class StationNotOwnedByPlayerError(Exception):
    pass


class FuelTypeNotFoundError(Exception):
    pass


class PriceOutOfBoundsError(Exception):
    pass


class PriceBelowCostError(Exception):
    pass


class PriceChangeCooldownError(Exception):
    pass


async def create_game_stations_for_game(
    db: AsyncSession, game_id: uuid.UUID, room_settings: GameSettings
) -> int:
    templates = (await db.execute(select(StationTemplate))).scalars().all()

    objects: list[GameStation | StationFuel] = []
    for template in templates:
        station_id = uuid.uuid4()
        objects.append(
            GameStation(
                id=station_id,
                game_id=game_id,
                station_template_id=template.id,
                purchase_price=template.base_price,
            )
        )
        starting_liters = room_settings.starting_station_capacity_liters * Decimal(
            str(room_settings.starting_fuel_fill_ratio)
        )
        for fuel_type, retail_price in _DEFAULT_RETAIL_PRICES.items():
            objects.append(
                StationFuel(
                    game_station_id=station_id,
                    fuel_type=fuel_type,
                    current_liters=starting_liters,
                    capacity_liters=room_settings.starting_station_capacity_liters,
                    retail_price=retail_price,
                )
            )

    db.add_all(objects)
    return len(templates)


def _station_query(game_id: uuid.UUID) -> Select[tuple[GameStation]]:
    return (
        select(GameStation)
        .where(GameStation.game_id == game_id)
        .options(
            selectinload(GameStation.station_template),
            selectinload(GameStation.owner).selectinload(GamePlayer.user),
            selectinload(GameStation.fuels),
        )
        .execution_options(populate_existing=True)
    )


async def list_game_stations(db: AsyncSession, game_id: uuid.UUID) -> list[GameStation]:
    stmt = _station_query(game_id).order_by(GameStation.created_at)
    result = await db.execute(stmt)
    return list(result.scalars())


async def get_game_station(
    db: AsyncSession, game_id: uuid.UUID, station_id: uuid.UUID
) -> GameStation:
    stmt = _station_query(game_id).where(GameStation.id == station_id)
    station = (await db.execute(stmt)).scalar_one_or_none()
    if station is None:
        raise StationNotFoundError
    return station


async def purchase_station(
    db: AsyncSession, game_id: uuid.UUID, station_id: uuid.UUID, user_id: uuid.UUID
) -> GameStation:
    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError

    if game.status != GameStatus.RUNNING:
        raise GameNotRunningError

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
            select(GameStation).where(GameStation.id == station_id, GameStation.game_id == game_id)
        )
    ).scalar_one_or_none()
    if station is None:
        raise StationNotFoundError

    claim_result = cast(
        CursorResult[Any],
        await db.execute(
            update(GameStation)
            .where(GameStation.id == station_id, GameStation.owner_player_id.is_(None))
            .values(owner_player_id=player.id)
        ),
    )
    if claim_result.rowcount != 1:
        await db.rollback()
        raise StationAlreadyOwnedError

    if player.balance < station.purchase_price:
        await db.rollback()
        raise InsufficientFundsError

    balance_before = player.balance
    player.balance = player.balance - station.purchase_price
    balance_after = player.balance

    db.add(
        FinancialTransaction(
            game_id=game_id,
            player_id=player.id,
            transaction_type=TRANSACTION_TYPE_STATION_PURCHASE,
            amount=-station.purchase_price,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type="game_station",
            reference_id=station.id,
        )
    )

    await db.commit()

    return await get_game_station(db, game_id, station_id)


def _validate_price_change(
    station_fuel: StationFuel, room_settings: GameSettings, retail_price: Decimal
) -> None:
    if not (
        room_settings.min_retail_price_per_liter
        <= retail_price
        <= room_settings.max_retail_price_per_liter
    ):
        raise PriceOutOfBoundsError

    if (
        not room_settings.allow_selling_below_cost
        and retail_price < station_fuel.average_purchase_price
    ):
        raise PriceBelowCostError

    if station_fuel.price_updated_at is not None:
        elapsed_seconds = (datetime.now(UTC) - station_fuel.price_updated_at).total_seconds()
        if elapsed_seconds < room_settings.price_change_cooldown_seconds:
            raise PriceChangeCooldownError


async def set_station_fuel_price(
    db: AsyncSession,
    game_id: uuid.UUID,
    station_id: uuid.UUID,
    user_id: uuid.UUID,
    fuel_type: FuelType,
    retail_price: Decimal,
) -> StationFuel:
    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError
    if game.status != GameStatus.RUNNING:
        raise GameNotRunningError

    room_settings = GameSettings.model_validate(game.settings_json)

    player = (
        await db.execute(
            select(GamePlayer).where(GamePlayer.game_id == game_id, GamePlayer.user_id == user_id)
        )
    ).scalar_one_or_none()
    if player is None:
        raise NotAGameMemberError

    station = (
        await db.execute(
            select(GameStation).where(GameStation.id == station_id, GameStation.game_id == game_id)
        )
    ).scalar_one_or_none()
    if station is None:
        raise StationNotFoundError
    if station.owner_player_id != player.id:
        raise StationNotOwnedByPlayerError

    station_fuel = (
        await db.execute(
            select(StationFuel).where(
                StationFuel.game_station_id == station_id, StationFuel.fuel_type == fuel_type
            )
        )
    ).scalar_one_or_none()
    if station_fuel is None:
        raise FuelTypeNotFoundError

    _validate_price_change(station_fuel, room_settings, retail_price)

    station_fuel.retail_price = retail_price
    station_fuel.price_updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(station_fuel)
    return station_fuel


async def set_network_fuel_price(
    db: AsyncSession,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
    fuel_type: FuelType,
    retail_price: Decimal,
) -> int:
    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError
    if game.status != GameStatus.RUNNING:
        raise GameNotRunningError

    room_settings = GameSettings.model_validate(game.settings_json)
    if not (
        room_settings.min_retail_price_per_liter
        <= retail_price
        <= room_settings.max_retail_price_per_liter
    ):
        raise PriceOutOfBoundsError

    player = (
        await db.execute(
            select(GamePlayer).where(GamePlayer.game_id == game_id, GamePlayer.user_id == user_id)
        )
    ).scalar_one_or_none()
    if player is None:
        raise NotAGameMemberError

    owned_station_ids = select(GameStation.id).where(
        GameStation.game_id == game_id, GameStation.owner_player_id == player.id
    )

    conditions = [
        StationFuel.fuel_type == fuel_type,
        StationFuel.game_station_id.in_(owned_station_ids),
    ]
    if not room_settings.allow_selling_below_cost:
        conditions.append(StationFuel.average_purchase_price <= retail_price)

    result = cast(
        CursorResult[Any],
        await db.execute(
            update(StationFuel)
            .where(*conditions)
            .values(retail_price=retail_price, price_updated_at=datetime.now(UTC))
        ),
    )

    await db.commit()
    return result.rowcount
