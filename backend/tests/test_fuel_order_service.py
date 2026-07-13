import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.fuel_order import FuelOrderStatus
from app.db.models.game_player import GamePlayer
from app.db.models.refinery import Refinery
from app.db.models.refinery_fuel import RefineryFuel
from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode
from app.db.models.station_fuel import FuelType, StationFuel
from app.db.models.station_template import StationTemplate
from app.db.models.truck import Truck, TruckStatus
from app.db.session import async_session_factory
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.services.auth_service import register_user
from app.services.fuel_order_service import (
    FuelOrderStopRequest,
    InsufficientFundsError,
    InsufficientRefineryStockError,
    StationCapacityExceededError,
    StationNotOwnedByPlayerError,
    TruckCapacityExceededError,
    create_fuel_order,
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


async def _seed_road_graph(*point_pairs: tuple[float, float]) -> None:
    """Connect every given (latitude, longitude) point to the next one with a two-way road."""
    async with async_session_factory() as db:
        nodes = [RoadNode(latitude=lat, longitude=lon) for lat, lon in point_pairs]
        db.add_all(nodes)
        await db.flush()
        for a, b in zip(nodes, nodes[1:], strict=False):
            db.add_all(
                [
                    RoadEdge(
                        from_node_id=a.id,
                        to_node_id=b.id,
                        distance_km=10.0,
                        max_speed_kmh=60.0,
                        road_type="local",
                    ),
                    RoadEdge(
                        from_node_id=b.id,
                        to_node_id=a.id,
                        distance_km=10.0,
                        max_speed_kmh=60.0,
                        road_type="local",
                    ),
                ]
            )
        await db.commit()


async def _setup_game(name: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Register creator, seed a station + refinery + road graph, start the game, buy the station.

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

    await _seed_road_graph((56.05, 47.05), (56.0, 47.0))

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
            db,
            game_id,
            creator_id,
            refinery_id,
            [
                FuelOrderStopRequest(
                    station_id=station_id, fuel_type=FuelType.AI92, liters=Decimal("2000")
                )
            ],
        )

    assert order.status == FuelOrderStatus.IN_TRANSIT
    assert order.total_cost > Decimal("0")
    assert order.completed_at is not None
    assert order.completed_at > order.started_at
    assert len(order.stops) == 1
    assert order.stops[0].position == 0

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

        truck = (
            await db.execute(select(Truck).where(Truck.fuel_order_id == order.id))
        ).scalar_one()
        assert truck.status == TruckStatus.EN_ROUTE
        assert truck.route_progress == 0.0
        assert truck.route_json["total_distance_km"] > 0


async def test_create_fuel_order_with_multiple_stops_orders_greedily(
    db_session: AsyncSession,
) -> None:
    name = "OrderMulti"
    async with async_session_factory() as db:
        db.add_all(
            [
                StationTemplate(
                    name=f"{name} Near",
                    latitude=56.01,
                    longitude=47.0,
                    base_price="2000000.00",
                    metadata_json={},
                ),
                StationTemplate(
                    name=f"{name} Far",
                    latitude=56.09,
                    longitude=47.0,
                    base_price="2000000.00",
                    metadata_json={},
                ),
            ]
        )
        db.add(Refinery(name=f"{name} Refinery", latitude=56.0, longitude=47.0))
        await db.commit()

    # refinery(56.0) -- near(56.01) -- far(56.09), a simple chain so the greedy
    # nearest-neighbor order must visit "near" before "far".
    await _seed_road_graph((56.0, 47.0), (56.01, 47.0), (56.09, 47.0))

    creator_id = await _register(f"{name.lower()}@example.com", "Owner")

    async with async_session_factory() as db:
        game = await create_game(db, creator_id, CreateGameRequest(name=name))
        game_id = game.id

    async with async_session_factory() as db:
        await start_game(db, game_id, creator_id)

    async with async_session_factory() as db:
        stations = await list_game_stations(db, game_id)
        near_station = next(s for s in stations if s.station_template.name == f"{name} Near")
        far_station = next(s for s in stations if s.station_template.name == f"{name} Far")

    async with async_session_factory() as db:
        await purchase_station(db, game_id, near_station.id, creator_id)
    async with async_session_factory() as db:
        await purchase_station(db, game_id, far_station.id, creator_id)

    async with async_session_factory() as db:
        refinery = (
            await db.execute(select(Refinery).where(Refinery.name == f"{name} Refinery"))
        ).scalar_one()

    async with async_session_factory() as db:
        # Request the far station first; the greedy planner should still visit
        # the near station first since it is physically closer.
        order = await create_fuel_order(
            db,
            game_id,
            creator_id,
            refinery.id,
            [
                FuelOrderStopRequest(
                    station_id=far_station.id, fuel_type=FuelType.AI92, liters=Decimal("1000")
                ),
                FuelOrderStopRequest(
                    station_id=near_station.id, fuel_type=FuelType.AI92, liters=Decimal("1000")
                ),
            ],
        )

    stops_by_station = {stop.station_id: stop for stop in order.stops}
    assert stops_by_station[near_station.id].position == 0
    assert stops_by_station[far_station.id].position == 1

    async with async_session_factory() as db:
        truck = (
            await db.execute(select(Truck).where(Truck.fuel_order_id == order.id))
        ).scalar_one()
        assert truck.route_json["total_distance_km"] == 20.0
        assert len(truck.route_json["stops"]) == 2


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

    await _seed_road_graph((56.05, 47.05), (56.0, 47.0))

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
                db,
                game_id,
                other_id,
                refinery_id,
                [
                    FuelOrderStopRequest(
                        station_id=station_id, fuel_type=FuelType.AI92, liters=Decimal("1000")
                    )
                ],
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
                db,
                game_id,
                creator_id,
                refinery_id,
                [
                    FuelOrderStopRequest(
                        station_id=station_id, fuel_type=FuelType.AI92, liters=Decimal("500")
                    )
                ],
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
                [
                    FuelOrderStopRequest(
                        station_id=station_id,
                        fuel_type=FuelType.AI92,
                        liters=Decimal("999999999"),
                    )
                ],
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
                db,
                game_id,
                creator_id,
                refinery_id,
                [
                    FuelOrderStopRequest(
                        station_id=station_id, fuel_type=FuelType.AI92, liters=Decimal("9000")
                    )
                ],
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
                db,
                game_id,
                creator_id,
                refinery_id,
                [
                    FuelOrderStopRequest(
                        station_id=station_id, fuel_type=FuelType.AI92, liters=Decimal("2000")
                    )
                ],
            )
            raised = None
        except InsufficientFundsError as exc:
            raised = exc

    assert isinstance(raised, InsufficientFundsError)
