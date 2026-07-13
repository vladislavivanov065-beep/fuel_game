import uuid
from collections import defaultdict
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
from app.db.models.truck import Truck, TruckStatus
from app.schemas.game_settings import GameSettings
from app.services import event_service, routing_service

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


class EmptyOrderError(Exception):
    pass


class RouteNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class FuelOrderStopRequest:
    station_id: uuid.UUID
    fuel_type: FuelType
    liters: Decimal


async def create_fuel_order(
    db: AsyncSession,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
    refinery_id: uuid.UUID,
    stops: list[FuelOrderStopRequest],
) -> FuelOrder:
    if not stops:
        raise EmptyOrderError

    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError
    if game.status != GameStatus.RUNNING:
        raise GameNotRunningError

    room_settings = GameSettings.model_validate(game.settings_json)
    event_modifiers, _ = await event_service.get_active_event_effects(db, game_id)

    total_liters = sum((stop.liters for stop in stops), Decimal("0"))
    if total_liters > room_settings.fuel_truck_capacity_liters:
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

    station_ids_in_order: list[uuid.UUID] = []
    seen_station_ids: set[uuid.UUID] = set()
    for stop in stops:
        if stop.station_id not in seen_station_ids:
            station_ids_in_order.append(stop.station_id)
            seen_station_ids.add(stop.station_id)

    stations_by_id: dict[uuid.UUID, GameStation] = {}
    for station_id in station_ids_in_order:
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
        stations_by_id[station_id] = station

    station_fuel_rows: dict[tuple[uuid.UUID, FuelType], StationFuel] = {}
    reserved_increment: dict[tuple[uuid.UUID, FuelType], Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    for stop in stops:
        key = (stop.station_id, stop.fuel_type)
        if key not in station_fuel_rows:
            row = (
                await db.execute(
                    select(StationFuel)
                    .where(
                        StationFuel.game_station_id == stop.station_id,
                        StationFuel.fuel_type == stop.fuel_type,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                raise FuelTypeNotFoundError
            station_fuel_rows[key] = row
        reserved_increment[key] += stop.liters

    for key, row in station_fuel_rows.items():
        reserved_total = row.current_liters + row.reserved_liters + reserved_increment[key]
        if reserved_total > row.capacity_liters:
            raise StationCapacityExceededError

    liters_by_fuel_type: dict[FuelType, Decimal] = defaultdict(lambda: Decimal("0"))
    for stop in stops:
        liters_by_fuel_type[stop.fuel_type] += stop.liters

    refinery_fuel_rows: dict[FuelType, RefineryFuel] = {}
    for fuel_type, liters in liters_by_fuel_type.items():
        refinery_fuel_row = (
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
        if refinery_fuel_row is None:
            raise FuelTypeNotFoundError
        if refinery_fuel_row.current_liters < liters:
            raise InsufficientRefineryStockError
        refinery_fuel_rows[fuel_type] = refinery_fuel_row

    nodes, edges = await routing_service.load_graph(
        db, traffic_multiplier=event_modifiers.traffic_multiplier
    )
    try:
        refinery_node = routing_service.find_nearest_node(
            nodes, refinery.latitude, refinery.longitude
        )
        station_node_by_id = {
            station_id: routing_service.find_nearest_node(
                nodes,
                stations_by_id[station_id].station_template.latitude,
                stations_by_id[station_id].station_template.longitude,
            )
            for station_id in station_ids_in_order
        }
        ordered_station_ids = routing_service.greedy_nearest_neighbor_order(
            nodes,
            edges,
            refinery_node.id,
            [
                (station_id, station_node_by_id[station_id].id)
                for station_id in station_ids_in_order
            ],
        )
        multi_route = routing_service.build_multi_stop_route(
            nodes,
            edges,
            [refinery_node.id] + [station_node_by_id[sid].id for sid in ordered_station_ids],
        )
    except routing_service.EmptyGraphError as exc:
        raise RouteNotFoundError from exc
    except routing_service.NoRouteFoundError as exc:
        raise RouteNotFoundError from exc

    refinery_price_multiplier = Decimal(str(event_modifiers.refinery_price_multiplier))
    fuel_cost = sum(
        (
            refinery_fuel_rows[stop.fuel_type].purchase_price
            * refinery_price_multiplier
            * stop.liters
            for stop in stops
        ),
        Decimal("0"),
    ).quantize(_CENTS, rounding=ROUND_HALF_UP)
    delivery_cost = (
        room_settings.base_delivery_fee
        + Decimal(str(multi_route.total_distance_km)) * room_settings.delivery_cost_per_km
    ).quantize(_CENTS, rounding=ROUND_HALF_UP)
    total_cost = fuel_cost + delivery_cost

    if player.balance < total_cost:
        raise InsufficientFundsError

    balance_before = player.balance
    balance_after = balance_before - total_cost
    player.balance = balance_after

    for fuel_type, refinery_fuel_row in refinery_fuel_rows.items():
        refinery_fuel_row.current_liters -= liters_by_fuel_type[fuel_type]

    for key, station_fuel_row in station_fuel_rows.items():
        station_fuel_row.reserved_liters += reserved_increment[key]

    now = datetime.now(UTC)
    completed_at = now + timedelta(minutes=multi_route.total_travel_time_minutes)

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

    position_by_station_id = {
        station_id: index for index, station_id in enumerate(ordered_station_ids)
    }
    for stop in stops:
        db.add(
            FuelOrderStop(
                fuel_order_id=order.id,
                station_id=stop.station_id,
                position=position_by_station_id[stop.station_id],
                fuel_type=stop.fuel_type,
                liters=stop.liters,
                status=FuelOrderStopStatus.PENDING,
            )
        )

    route_json = routing_service.serialize_multi_stop_route(
        multi_route, list(range(len(ordered_station_ids)))
    )
    start_point = multi_route.points[0]
    db.add(
        Truck(
            game_id=game_id,
            fuel_order_id=order.id,
            status=TruckStatus.EN_ROUTE,
            route_json=route_json,
            route_progress=0.0,
            current_latitude=start_point.latitude,
            current_longitude=start_point.longitude,
            started_at=now,
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


async def list_my_trucks(db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID) -> list[Truck]:
    player = (
        await db.execute(
            select(GamePlayer).where(GamePlayer.game_id == game_id, GamePlayer.user_id == user_id)
        )
    ).scalar_one_or_none()
    if player is None:
        raise NotAGameMemberError

    trucks = (
        (
            await db.execute(
                select(Truck)
                .join(FuelOrder, FuelOrder.id == Truck.fuel_order_id)
                .where(Truck.game_id == game_id, FuelOrder.player_id == player.id)
                .order_by(Truck.started_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(trucks)
