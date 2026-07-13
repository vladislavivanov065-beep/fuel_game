import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models.game_room import GameRoom, GameStatus
from app.db.models.truck import Truck
from app.db.session import async_session_factory
from app.schemas.game_settings import GameSettings
from app.simulation import economy, trucks
from app.websocket.connection_manager import connection_manager

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 1.0
_TRUCK_BROADCAST_INTERVAL_SECONDS = 3.0

_task: asyncio.Task[None] | None = None
_last_tick_at: dict[uuid.UUID, datetime] = {}
_last_truck_broadcast_at: dict[uuid.UUID, datetime] = {}


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


async def _run_tick_cycle() -> None:
    now = datetime.now(UTC)
    games = await _running_games()

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

    for game in games:
        await _update_trucks(game.id, now)


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
