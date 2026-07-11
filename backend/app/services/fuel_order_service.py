import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.financial_transaction import (
    TRANSACTION_TYPE_FUEL_ORDER,
    FinancialTransaction,
)
from app.db.models.fuel_order import FuelOrder, FuelOrderStatus
from app.db.models.fuel_order_stop import FuelOrderStop, FuelOrderStopStatus
from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom, GameStatus
from app.db.models.game_station import GameStation
from app.db.models.refinery import Refinery
from app.db.models.refinery_fuel import RefineryFuel
from app.db.models.station_fuel import FuelType, StationFuel
from app.schemas.game_settings import GameSettings

_EARTH_RADIUS_KM = 6371.0
_CENTS = Decimal("0.01")


class GameNotFoundError(Exception):
    pass


class GameNotRunningError(Exception):
    pass


class NotAGameMemberError(Exception):
    pass


class RefineryNotFoundError(Exception):
    pass


class StationNotFoundError(Exception):
    pass


class StationNotOwnedByPlayerError(Exception):
    pass


class FuelTypeNotFoundError(Exception):
    pass


class TruckCapacityExceededError(Exception):
    pass


class StationCapacityExceededError(Exception):
    pass


class InsufficientRefineryStockError(Exception):
    pass


class InsufficientFundsError(Exception):
    pass


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


async def create_fuel_order(
    db: AsyncSession,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
    refinery_id: uuid.UUID,
    station_id: uuid.UUID,
    fuel_type: FuelType,
    liters: Decimal,
) -> FuelOrder:
    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError
    if game.status != GameStatus.RUNNING:
        raise GameNotRunningError

    room_settings = GameSettings.model_validate(game.settings_json)
    if liters > room_settings.fuel_truck_capacity_liters:
        raise TruckCapacityExceededError

    player = (
        await db.execute(
            select(GamePlayer)
            .where(GamePlayer.game_id == game_id, GamePlayer.user_id == user_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if player is None:
        raise NotAGameMemberError

    refinery = (
        await db.execute(select(Refinery).where(Refinery.id == refinery_id))
    ).scalar_one_or_none()
    if refinery is None:
        raise RefineryNotFoundError

    station = (
        await db.execute(
            select(GameStation)
            .where(GameStation.id == station_id, GameStation.game_id == game_id)
            .options(selectinload(GameStation.station_template))
        )
    ).scalar_one_or_none()
    if station is None:
        raise StationNotFoundError
    if station.owner_player_id != player.id:
        raise StationNotOwnedByPlayerError

    refinery_fuel = (
        await db.execute(
            select(RefineryFuel)
            .where(
                RefineryFuel.refinery_id == refinery_id,
                RefineryFuel.game_id == game_id,
                RefineryFuel.fuel_type == fuel_type,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if refinery_fuel is None:
        raise FuelTypeNotFoundError
    if refinery_fuel.current_liters < liters:
        raise InsufficientRefineryStockError

    station_fuel = (
        await db.execute(
            select(StationFuel)
            .where(StationFuel.game_station_id == station_id, StationFuel.fuel_type == fuel_type)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if station_fuel is None:
        raise FuelTypeNotFoundError
    reserved_total = station_fuel.current_liters + station_fuel.reserved_liters + liters
    if reserved_total > station_fuel.capacity_liters:
        raise StationCapacityExceededError

    distance_km = Decimal(
        str(
            _haversine_km(
                refinery.latitude,
                refinery.longitude,
                station.station_template.latitude,
                station.station_template.longitude,
            )
        )
    )

    fuel_cost = (refinery_fuel.purchase_price * liters).quantize(_CENTS, rounding=ROUND_HALF_UP)
    delivery_cost = (
        room_settings.base_delivery_fee + distance_km * room_settings.delivery_cost_per_km
    ).quantize(_CENTS, rounding=ROUND_HALF_UP)
    total_cost = fuel_cost + delivery_cost

    if player.balance < total_cost:
        raise InsufficientFundsError

    balance_before = player.balance
    balance_after = balance_before - total_cost
    player.balance = balance_after

    refinery_fuel.current_liters -= liters
    station_fuel.reserved_liters += liters

    now = datetime.now(UTC)
    travel_minutes = (float(distance_km) / room_settings.truck_speed_kmh) * 60.0
    loading_minutes = float(liters) / refinery_fuel.loading_speed
    completed_at = now + timedelta(minutes=travel_minutes + loading_minutes)

    order = FuelOrder(
        game_id=game_id,
        player_id=player.id,
        refinery_id=refinery_id,
        status=FuelOrderStatus.IN_TRANSIT,
        total_cost=total_cost,
        delivery_cost=delivery_cost,
        started_at=now,
        completed_at=completed_at,
    )
    db.add(order)
    await db.flush()

    db.add(
        FuelOrderStop(
            fuel_order_id=order.id,
            station_id=station_id,
            position=0,
            fuel_type=fuel_type,
            liters=liters,
            status=FuelOrderStopStatus.PENDING,
        )
    )
    db.add(
        FinancialTransaction(
            game_id=game_id,
            player_id=player.id,
            transaction_type=TRANSACTION_TYPE_FUEL_ORDER,
            amount=-total_cost,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type="fuel_order",
            reference_id=order.id,
        )
    )

    await db.commit()
    await db.refresh(order, attribute_names=["stops"])
    return order


@dataclass(frozen=True)
class DeliveredOrderResult:
    order_id: uuid.UUID
    player_id: uuid.UUID
    station_id: uuid.UUID
    fuel_type: FuelType
    liters: Decimal


async def deliver_due_fuel_orders(
    db: AsyncSession, game_id: uuid.UUID
) -> list[DeliveredOrderResult]:
    """Finalize deliveries whose planned arrival time has passed.

    Batch-checked from the scheduler loop rather than a per-order timer,
    per the project's rule against a background task per entity.
    """
    now = datetime.now(UTC)
    orders = (
        (
            await db.execute(
                select(FuelOrder).where(
                    FuelOrder.game_id == game_id,
                    FuelOrder.status == FuelOrderStatus.IN_TRANSIT,
                    FuelOrder.completed_at <= now,
                )
            )
        )
        .scalars()
        .all()
    )
    if not orders:
        return []

    results: list[DeliveredOrderResult] = []
    for order in orders:
        stops = (
            (
                await db.execute(
                    select(FuelOrderStop)
                    .where(FuelOrderStop.fuel_order_id == order.id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        for stop in stops:
            station_fuel = (
                await db.execute(
                    select(StationFuel)
                    .where(
                        StationFuel.game_station_id == stop.station_id,
                        StationFuel.fuel_type == stop.fuel_type,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if station_fuel is None:
                stop.status = FuelOrderStopStatus.FAILED
                continue

            station_fuel.current_liters += stop.liters
            station_fuel.reserved_liters -= stop.liters
            stop.delivered_liters = stop.liters
            stop.status = FuelOrderStopStatus.DELIVERED
            results.append(
                DeliveredOrderResult(
                    order_id=order.id,
                    player_id=order.player_id,
                    station_id=stop.station_id,
                    fuel_type=stop.fuel_type,
                    liters=stop.liters,
                )
            )

        order.status = FuelOrderStatus.DELIVERED

    await db.commit()
    return results


async def list_my_fuel_orders(
    db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID
) -> list[FuelOrder]:
    player = (
        await db.execute(
            select(GamePlayer).where(GamePlayer.game_id == game_id, GamePlayer.user_id == user_id)
        )
    ).scalar_one_or_none()
    if player is None:
        raise NotAGameMemberError

    orders = (
        (
            await db.execute(
                select(FuelOrder)
                .where(FuelOrder.game_id == game_id, FuelOrder.player_id == player.id)
                .options(selectinload(FuelOrder.stops))
                .order_by(FuelOrder.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(orders)
