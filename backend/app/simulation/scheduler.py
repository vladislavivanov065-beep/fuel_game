import asyncio
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.db.models.game_room import GameRoom, GameStatus
from app.db.models.truck import Truck
from app.db.models.vehicle import Vehicle
from app.db.session import async_session_factory
from app.schemas.game_settings import GameSettings
from app.simulation import (
    economy,
    events,
    game_lifecycle,
    station_upgrades,
    trades,
    trucks,
    vehicles,
)
from app.websocket.connection_manager import connection_manager

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 1.0
_TRUCK_BROADCAST_INTERVAL_SECONDS = 3.0
_VEHICLE_BROADCAST_INTERVAL_SECONDS = 3.0

_task: asyncio.Task[None] | None = None
_last_tick_at: dict[uuid.UUID, datetime] = {}
_last_truck_broadcast_at: dict[uuid.UUID, datetime] = {}
_last_vehicle_broadcast_at: dict[uuid.UUID, datetime] = {}
_last_event_check_at: dict[uuid.UUID, datetime] = {}


async def _broadcast_tick_result(game_id: uuid.UUID, result: economy.EconomicTickResult) -> None:
    if not result.station_sales:
        return

    await connection_manager.broadcast(
        game_id,
        "economy.tick",
        {
            "station_sales": [
                {
                    "station_id": str(sale.station_id),
                    "fuel_type": sale.fuel_type,
                    "liters_sold": str(sale.liters_sold),
                    "total_amount": str(sale.total_amount),
                    "profit_amount": str(sale.profit_amount),
                }
                for sale in result.station_sales
            ],
            "player_revenues": [
                {
                    "player_id": str(revenue.player_id),
                    "revenue": str(revenue.revenue),
                    "balance_after": str(revenue.balance_after),
                }
                for revenue in result.player_revenues
            ],
        },
    )


async def _running_games() -> list[GameRoom]:
    async with async_session_factory() as db:
        return list(
            (await db.execute(select(GameRoom).where(GameRoom.status == GameStatus.RUNNING)))
            .scalars()
            .all()
        )


def _due_game_ids(games: list[GameRoom], now: datetime) -> list[uuid.UUID]:
    due: list[uuid.UUID] = []
    for game in games:
        interval = GameSettings.model_validate(game.settings_json).economic_tick_interval_seconds
        last = _last_tick_at.get(game.id)
        if last is None or (now - last).total_seconds() >= interval:
            due.append(game.id)
    return due


async def _broadcast_truck_tick(
    game_id: uuid.UUID, result: trucks.TruckTickResult, now: datetime
) -> None:
    for stop in result.delivered_stops:
        await connection_manager.broadcast(
            game_id,
            "fuel_order.delivered",
            {
                "order_id": str(stop.order_id),
                "player_id": str(stop.player_id),
                "station_id": str(stop.station_id),
                "fuel_type": stop.fuel_type.value,
                "liters": str(stop.liters),
            },
        )

    for truck_id in result.rerouted_truck_ids:
        await connection_manager.broadcast(game_id, "truck.rerouted", {"truck_id": str(truck_id)})

    last_broadcast = _last_truck_broadcast_at.get(game_id)
    due = (
        last_broadcast is None
        or (now - last_broadcast).total_seconds() >= _TRUCK_BROADCAST_INTERVAL_SECONDS
    )
    if result.updated_truck_ids and due:
        _last_truck_broadcast_at[game_id] = now
        async with async_session_factory() as db:
            truck_rows = (
                await db.execute(select(Truck).where(Truck.id.in_(result.updated_truck_ids)))
            ).scalars()
            await connection_manager.broadcast(
                game_id,
                "truck.updated",
                {
                    "trucks": [
                        {
                            "truck_id": str(truck.id),
                            "fuel_order_id": str(truck.fuel_order_id),
                            "latitude": truck.current_latitude,
                            "longitude": truck.current_longitude,
                            "progress": truck.route_progress,
                            "status": truck.status.value,
                        }
                        for truck in truck_rows
                    ]
                },
            )


async def _update_trucks(game_id: uuid.UUID, now: datetime) -> None:
    async with async_session_factory() as db:
        try:
            result = await trucks.update_trucks_for_game(db, game_id)
        except Exception:
            logger.exception("Truck update failed for game %s", game_id)
            return

    await _broadcast_truck_tick(game_id, result, now)


async def _broadcast_vehicle_tick(
    game_id: uuid.UUID, result: vehicles.VehicleTickResult, now: datetime
) -> None:
    for purchase in result.purchases:
        await connection_manager.broadcast(
            game_id,
            "vehicle.fuel_purchase",
            {
                "vehicle_id": str(purchase.vehicle_id),
                "station_id": str(purchase.station_id),
                "player_id": str(purchase.player_id),
                "fuel_type": purchase.fuel_type.value,
                "liters": str(purchase.liters),
                "total_amount": str(purchase.total_amount),
            },
        )

    if result.arrived_vehicle_ids:
        await connection_manager.broadcast(
            game_id,
            "vehicle.arrived",
            {"vehicle_ids": [str(vehicle_id) for vehicle_id in result.arrived_vehicle_ids]},
        )

    last_broadcast = _last_vehicle_broadcast_at.get(game_id)
    due = (
        last_broadcast is None
        or (now - last_broadcast).total_seconds() >= _VEHICLE_BROADCAST_INTERVAL_SECONDS
    )
    if result.updated_vehicle_ids and due:
        _last_vehicle_broadcast_at[game_id] = now
        async with async_session_factory() as db:
            vehicle_rows = (
                await db.execute(select(Vehicle).where(Vehicle.id.in_(result.updated_vehicle_ids)))
            ).scalars()
            await connection_manager.broadcast(
                game_id,
                "vehicle.updated",
                {
                    "vehicles": [
                        {
                            "vehicle_id": str(vehicle.id),
                            "vehicle_type": vehicle.vehicle_type.value,
                            "latitude": vehicle.current_latitude,
                            "longitude": vehicle.current_longitude,
                            "heading": vehicle.heading,
                            "progress": vehicle.route_progress,
                            "status": vehicle.status.value,
                        }
                        for vehicle in vehicle_rows
                    ]
                },
            )


async def _update_vehicles(game_id: uuid.UUID, now: datetime) -> None:
    async with async_session_factory() as db:
        try:
            await vehicles.spawn_vehicles_for_game(db, game_id)
        except Exception:
            logger.exception("Vehicle spawn failed for game %s", game_id)

    async with async_session_factory() as db:
        try:
            result = await vehicles.update_vehicles_for_game(db, game_id)
        except Exception:
            logger.exception("Vehicle update failed for game %s", game_id)
            return

    await _broadcast_vehicle_tick(game_id, result, now)


async def _broadcast_upgrade_tick(
    game_id: uuid.UUID, result: station_upgrades.UpgradeTickResult
) -> None:
    for upgrade_id in result.activated_upgrade_ids:
        await connection_manager.broadcast(
            game_id, "station_upgrade.completed", {"upgrade_id": str(upgrade_id)}
        )
    for upgrade_id in result.expired_upgrade_ids:
        await connection_manager.broadcast(
            game_id, "station_upgrade.expired", {"upgrade_id": str(upgrade_id)}
        )


async def _update_station_upgrades(game_id: uuid.UUID) -> None:
    async with async_session_factory() as db:
        try:
            result = await station_upgrades.complete_due_upgrades_for_game(db, game_id)
        except Exception:
            logger.exception("Station upgrade tick failed for game %s", game_id)
            return

    if result.activated_upgrade_ids or result.expired_upgrade_ids:
        await _broadcast_upgrade_tick(game_id, result)


def _due_for_event_check(games: list[GameRoom], now: datetime) -> list[uuid.UUID]:
    due: list[uuid.UUID] = []
    for game in games:
        interval = GameSettings.model_validate(game.settings_json).event_check_interval_seconds
        last = _last_event_check_at.get(game.id)
        if last is None or (now - last).total_seconds() >= interval:
            due.append(game.id)
    return due


async def _roll_event(game_id: uuid.UUID) -> None:
    async with async_session_factory() as db:
        try:
            event = await events.roll_random_event_for_game(db, game_id)
        except Exception:
            logger.exception("Event roll failed for game %s", game_id)
            return

    if event is not None:
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


async def _expire_events(game_id: uuid.UUID) -> None:
    async with async_session_factory() as db:
        try:
            expired_ids = await events.expire_due_events_for_game(db, game_id)
        except Exception:
            logger.exception("Event expiry failed for game %s", game_id)
            return

    for event_id in expired_ids:
        await connection_manager.broadcast(game_id, "game_event.ended", {"event_id": str(event_id)})


async def _expire_trade_offers(game_id: uuid.UUID) -> None:
    async with async_session_factory() as db:
        try:
            expired_ids = await trades.expire_due_trade_offers_for_game(db, game_id)
        except Exception:
            logger.exception("Trade offer expiry failed for game %s", game_id)
            return

    for trade_id in expired_ids:
        await connection_manager.broadcast(game_id, "trade.expired", {"trade_id": str(trade_id)})


async def _finish_due_games(games: list[GameRoom]) -> list[GameRoom]:
    remaining: list[GameRoom] = []
    for game in games:
        net_worth: dict[uuid.UUID, Decimal] | None = None
        async with async_session_factory() as db:
            try:
                fresh_game = await db.get(GameRoom, game.id)
                if fresh_game is not None:
                    net_worth = await game_lifecycle.maybe_finish_game(db, fresh_game)
            except Exception:
                logger.exception("Game finish check failed for game %s", game.id)

        if net_worth is None:
            remaining.append(game)
            continue

        leaderboard = sorted(
            ({"player_id": str(pid), "net_worth": str(value)} for pid, value in net_worth.items()),
            key=lambda row: Decimal(row["net_worth"]),
            reverse=True,
        )
        await connection_manager.broadcast(game.id, "game.finished", {"leaderboard": leaderboard})

    return remaining


async def _run_tick_cycle() -> None:
    now = datetime.now(UTC)
    games = await _finish_due_games(await _running_games())

    for game_id in _due_game_ids(games, now):
        async with async_session_factory() as db:
            try:
                result = await economy.run_economic_tick_for_game(db, game_id)
            except (economy.GameNotFoundError, economy.GameNotRunningError):
                continue
            except Exception:
                logger.exception("Economic tick failed for game %s", game_id)
                continue

        _last_tick_at[game_id] = datetime.now(UTC)
        await _broadcast_tick_result(game_id, result)

    for game_id in _due_for_event_check(games, now):
        _last_event_check_at[game_id] = now
        await _roll_event(game_id)

    for game in games:
        await _update_trucks(game.id, now)
        await _update_vehicles(game.id, now)
        await _update_station_upgrades(game.id)
        await _expire_events(game.id)
        await _expire_trade_offers(game.id)


async def _run_forever() -> None:
    while True:
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        try:
            await _run_tick_cycle()
        except Exception:
            logger.exception("Economic tick loop iteration failed")


def start() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_run_forever())


async def stop() -> None:
    global _task
    if _task is None:
        return

    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
