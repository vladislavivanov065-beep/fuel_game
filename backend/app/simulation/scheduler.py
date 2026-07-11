import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models.game_room import GameRoom, GameStatus
from app.db.session import async_session_factory
from app.schemas.game_settings import GameSettings
from app.services import fuel_order_service
from app.simulation import economy
from app.websocket.connection_manager import connection_manager

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 1.0

_task: asyncio.Task[None] | None = None
_last_tick_at: dict[uuid.UUID, datetime] = {}


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


async def _broadcast_delivered_orders(
    game_id: uuid.UUID, delivered: list[fuel_order_service.DeliveredOrderResult]
) -> None:
    for order in delivered:
        await connection_manager.broadcast(
            game_id,
            "fuel_order.delivered",
            {
                "order_id": str(order.order_id),
                "player_id": str(order.player_id),
                "station_id": str(order.station_id),
                "fuel_type": order.fuel_type.value,
                "liters": str(order.liters),
            },
        )


async def _deliver_fuel_orders(game_id: uuid.UUID) -> None:
    async with async_session_factory() as db:
        try:
            delivered = await fuel_order_service.deliver_due_fuel_orders(db, game_id)
        except Exception:
            logger.exception("Fuel order delivery failed for game %s", game_id)
            return

    await _broadcast_delivered_orders(game_id, delivered)


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
        await _deliver_fuel_orders(game.id)


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
