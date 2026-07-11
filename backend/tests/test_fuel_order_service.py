import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.fuel_order import FuelOrder, FuelOrderStatus
from app.db.models.fuel_order_stop import FuelOrderStop, FuelOrderStopStatus
from app.db.models.game_player import GamePlayer
from app.db.models.refinery import Refinery
from app.db.models.refinery_fuel import RefineryFuel
from app.db.models.station_fuel import FuelType, StationFuel
from app.db.models.station_template import StationTemplate
from app.db.session import async_session_factory
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.services.auth_service import register_user
from app.services.fuel_order_service import (
    InsufficientFundsError,
    InsufficientRefineryStockError,
    StationCapacityExceededError,
    StationNotOwnedByPlayerError,
    TruckCapacityExceededError,
    create_fuel_order,
    deliver_due_fuel_orders,
)
from app.services.game_service import create_game, join_game, start_game
from app.services.station_service import list_game_stations, purchase_station


async def _register(email: str, display_name: str = "Player") -> uuid.UUID:
    async with async_session_factory() as db:
        user, _ = await register_user(
            db,
            RegisterRequest(email=email, password="correcthorsebattery", display_name=display_name),
        )
        return user.id


async def _setup_game(name: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Register creator, seed a station + refinery, start the game, buy the station.

    Returns (game_id, creator_id, station_id, refinery_id).
    """
    async with async_session_factory() as db:
        db.add(
            StationTemplate(
                name=f"{name} Station",
                latitude=56.0,
                longitude=47.0,
                base_price="2000000.00",
                metadata_json={},
            )
        )
        db.add(Refinery(name=f"{name} Refinery", latitude=56.05, longitude=47.05))
        await db.commit()

    creator_id = await _register(f"{name.lower()}@example.com", "Owner")

    async with async_session_factory() as db:
        game = await create_game(db, creator_id, CreateGameRequest(name=name))
        game_id = game.id

    async with async_session_factory() as db:
        await start_game(db, game_id, creator_id)

    async with async_session_factory() as db:
        stations = await list_game_stations(db, game_id)
        station_id = stations[0].id

    async with async_session_factory() as db:
        await purchase_station(db, game_id, station_id, creator_id)

    async with async_session_factory() as db:
        refinery = (
            await db.execute(select(Refinery).where(Refinery.name == f"{name} Refinery"))
        ).scalar_one()
        refinery_id = refinery.id

    return game_id, creator_id, station_id, refinery_id


async def test_create_fuel_order_succeeds_and_reserves_stock(db_session: AsyncSession) -> None:
    game_id, creator_id, station_id, refinery_id = await _setup_game("OrderOk")

    async with async_session_factory() as db:
        order = await create_fuel_order(
            db, game_id, creator_id, refinery_id, station_id, FuelType.AI92, Decimal("2000")
        )

    assert order.status == FuelOrderStatus.IN_TRANSIT
    assert order.total_cost > Decimal("0")
    assert order.completed_at is not None
    assert order.completed_at > order.started_at

    async with async_session_factory() as db:
        station_fuel = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        assert station_fuel.reserved_liters == Decimal("2000.00")

        player = (
            await db.execute(select(GamePlayer).where(GamePlayer.id == order.player_id))
        ).scalar_one()
        assert player.balance == Decimal("5000000.00") - Decimal("2000000.00") - order.total_cost


async def test_create_fuel_order_rejects_non_owner(db_session: AsyncSession) -> None:
    name = "OrderOwner"
    async with async_session_factory() as db:
        db.add(
            StationTemplate(
                name=f"{name} Station",
                latitude=56.0,
                longitude=47.0,
                base_price="2000000.00",
                metadata_json={},
            )
        )
        db.add(Refinery(name=f"{name} Refinery", latitude=56.05, longitude=47.05))
        await db.commit()

    creator_id = await _register(f"{name.lower()}@example.com", "Owner")
    other_id = await _register("orderowner_other@example.com", "Other")

    async with async_session_factory() as db:
        game = await create_game(db, creator_id, CreateGameRequest(name=name))
        game_id = game.id
        invite_code = game.invite_code

    async with async_session_factory() as db:
        await join_game(db, game_id, other_id, invite_code)

    async with async_session_factory() as db:
        await start_game(db, game_id, creator_id)

    async with async_session_factory() as db:
        stations = await list_game_stations(db, game_id)
        station_id = stations[0].id

    async with async_session_factory() as db:
        await purchase_station(db, game_id, station_id, creator_id)

    async with async_session_factory() as db:
        refinery = (
            await db.execute(select(Refinery).where(Refinery.name == f"{name} Refinery"))
        ).scalar_one()
        refinery_id = refinery.id

    async with async_session_factory() as db:
        try:
            await create_fuel_order(
                db, game_id, other_id, refinery_id, station_id, FuelType.AI92, Decimal("1000")
            )
            raised = None
        except StationNotOwnedByPlayerError as exc:
            raised = exc

    assert isinstance(raised, StationNotOwnedByPlayerError)


async def test_create_fuel_order_rejects_insufficient_refinery_stock(
    db_session: AsyncSession,
) -> None:
    game_id, creator_id, station_id, refinery_id = await _setup_game("OrderStock")

    async with async_session_factory() as db:
        await db.execute(
            update(RefineryFuel)
            .where(RefineryFuel.refinery_id == refinery_id, RefineryFuel.fuel_type == FuelType.AI92)
            .values(current_liters=Decimal("100.00"))
        )
        await db.commit()

    async with async_session_factory() as db:
        try:
            await create_fuel_order(
                db, game_id, creator_id, refinery_id, station_id, FuelType.AI92, Decimal("500")
            )
            raised = None
        except InsufficientRefineryStockError as exc:
            raised = exc

    assert isinstance(raised, InsufficientRefineryStockError)


async def test_create_fuel_order_rejects_truck_capacity_exceeded(
    db_session: AsyncSession,
) -> None:
    game_id, creator_id, station_id, refinery_id = await _setup_game("OrderTruck")

    async with async_session_factory() as db:
        try:
            await create_fuel_order(
                db,
                game_id,
                creator_id,
                refinery_id,
                station_id,
                FuelType.AI92,
                Decimal("999999999"),
            )
            raised = None
        except TruckCapacityExceededError as exc:
            raised = exc

    assert isinstance(raised, TruckCapacityExceededError)


async def test_create_fuel_order_rejects_station_capacity_exceeded(
    db_session: AsyncSession,
) -> None:
    game_id, creator_id, station_id, refinery_id = await _setup_game("OrderCap")

    async with async_session_factory() as db:
        try:
            await create_fuel_order(
                db, game_id, creator_id, refinery_id, station_id, FuelType.AI92, Decimal("9000")
            )
            raised = None
        except StationCapacityExceededError as exc:
            raised = exc

    assert isinstance(raised, StationCapacityExceededError)


async def test_create_fuel_order_rejects_insufficient_funds(db_session: AsyncSession) -> None:
    game_id, creator_id, station_id, refinery_id = await _setup_game("OrderFunds")

    async with async_session_factory() as db:
        await db.execute(
            update(GamePlayer).where(GamePlayer.game_id == game_id).values(balance=Decimal("1.00"))
        )
        await db.commit()

    async with async_session_factory() as db:
        try:
            await create_fuel_order(
                db, game_id, creator_id, refinery_id, station_id, FuelType.AI92, Decimal("2000")
            )
            raised = None
        except InsufficientFundsError as exc:
            raised = exc

    assert isinstance(raised, InsufficientFundsError)


async def test_deliver_due_fuel_orders_credits_station_and_marks_delivered(
    db_session: AsyncSession,
) -> None:
    game_id, creator_id, station_id, refinery_id = await _setup_game("OrderDeliver")

    async with async_session_factory() as db:
        order = await create_fuel_order(
            db, game_id, creator_id, refinery_id, station_id, FuelType.AI92, Decimal("2000")
        )

    async with async_session_factory() as db:
        fuel_before = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        liters_before = fuel_before.current_liters

    async with async_session_factory() as db:
        await db.execute(
            update(FuelOrder)
            .where(FuelOrder.id == order.id)
            .values(completed_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await db.commit()

    async with async_session_factory() as db:
        delivered = await deliver_due_fuel_orders(db, game_id)

    assert len(delivered) == 1
    assert delivered[0].order_id == order.id
    assert delivered[0].station_id == station_id
    assert delivered[0].liters == Decimal("2000.00")

    async with async_session_factory() as db:
        order_row = await db.get(FuelOrder, order.id)
        assert order_row is not None
        assert order_row.status == FuelOrderStatus.DELIVERED

        stop_row = (
            await db.execute(select(FuelOrderStop).where(FuelOrderStop.fuel_order_id == order.id))
        ).scalar_one()
        assert stop_row.status == FuelOrderStopStatus.DELIVERED
        assert stop_row.delivered_liters == Decimal("2000.00")

        fuel_after = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        assert fuel_after.current_liters == liters_before + Decimal("2000.00")
        assert fuel_after.reserved_liters == Decimal("0.00")


async def test_deliver_due_fuel_orders_waits_for_real_delay(db_session: AsyncSession) -> None:
    game_id, creator_id, station_id, refinery_id = await _setup_game("OrderRealDelay")

    async with async_session_factory() as db:
        order = await create_fuel_order(
            db, game_id, creator_id, refinery_id, station_id, FuelType.AI92, Decimal("500")
        )

    async with async_session_factory() as db:
        await db.execute(
            update(FuelOrder)
            .where(FuelOrder.id == order.id)
            .values(completed_at=datetime.now(UTC) + timedelta(seconds=1))
        )
        await db.commit()

    async with async_session_factory() as db:
        too_early = await deliver_due_fuel_orders(db, game_id)
    assert too_early == []

    await asyncio.sleep(1.5)

    async with async_session_factory() as db:
        delivered = await deliver_due_fuel_orders(db, game_id)
    assert len(delivered) == 1
    assert delivered[0].order_id == order.id
