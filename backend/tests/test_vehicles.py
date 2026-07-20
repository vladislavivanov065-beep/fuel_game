import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.financial_transaction import FinancialTransaction
from app.db.models.fuel_sale import FuelSale
from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom
from app.db.models.game_station import GameStation
from app.db.models.refinery import Refinery
from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode
from app.db.models.station_fuel import FuelType, StationFuel
from app.db.models.station_template import StationTemplate
from app.db.models.station_upgrade import StationUpgrade, UpgradeStatus, UpgradeType
from app.db.models.vehicle import DriverType, Vehicle, VehicleStatus
from app.db.session import async_session_factory
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.schemas.game_settings import GameSettings
from app.services import routing_service, station_service
from app.services.auth_service import register_user
from app.services.game_service import create_game, start_game
from app.services.station_upgrade_service import purchase_upgrade
from app.simulation import vehicles as vehicles_module
from app.simulation.vehicles import (
    DriverProfile,
    StationCandidate,
    choose_station_index,
    compute_station_score,
    sample_driver_profile,
    spawn_vehicles_for_game,
    update_vehicles_for_game,
)


def _profile(**overrides: float) -> DriverProfile:
    base = {
        "price_sensitivity": 1.0,
        "distance_sensitivity": 1.0,
        "queue_sensitivity": 1.0,
        "rating_sensitivity": 1.0,
    }
    base.update(overrides)
    return DriverProfile(**base)


def test_compute_station_score_rewards_cheaper_price_for_price_sensitive_driver() -> None:
    settings = GameSettings()
    cheap = StationCandidate(
        station_id=uuid.uuid4(),
        retail_price=Decimal("50.00"),
        detour_km=1.0,
        queue_length=0,
        rating=4.0,
    )
    expensive = StationCandidate(
        station_id=uuid.uuid4(),
        retail_price=Decimal("70.00"),
        detour_km=1.0,
        queue_length=0,
        rating=4.0,
    )
    profile = _profile(price_sensitivity=2.0)

    cheap_score = compute_station_score(
        cheap,
        cheapest_available_price=Decimal("50.00"),
        profile=profile,
        settings=settings,
        random_factor=0.0,
    )
    expensive_score = compute_station_score(
        expensive,
        cheapest_available_price=Decimal("50.00"),
        profile=profile,
        settings=settings,
        random_factor=0.0,
    )
    assert cheap_score > expensive_score


def test_compute_station_score_penalizes_queue_for_queue_sensitive_driver() -> None:
    settings = GameSettings()
    empty_queue = StationCandidate(
        station_id=uuid.uuid4(),
        retail_price=Decimal("50.00"),
        detour_km=1.0,
        queue_length=0,
        rating=4.0,
    )
    long_queue = StationCandidate(
        station_id=uuid.uuid4(),
        retail_price=Decimal("50.00"),
        detour_km=1.0,
        queue_length=10,
        rating=4.0,
    )
    profile = _profile(queue_sensitivity=2.0)

    empty_score = compute_station_score(
        empty_queue,
        cheapest_available_price=Decimal("50.00"),
        profile=profile,
        settings=settings,
        random_factor=0.0,
    )
    long_score = compute_station_score(
        long_queue,
        cheapest_available_price=Decimal("50.00"),
        profile=profile,
        settings=settings,
        random_factor=0.0,
    )
    assert empty_score > long_score


def test_choose_station_index_prefers_higher_score_over_many_trials() -> None:
    rng = random.Random(42)
    scores = [0.5, 3.0, 0.1]
    counts = [0, 0, 0]
    for _ in range(500):
        counts[choose_station_index(scores, rng)] += 1
    assert counts[1] > counts[0] > counts[2]


def test_sample_driver_profile_economical_is_more_price_sensitive_than_premium() -> None:
    rng = random.Random(7)
    economical = sample_driver_profile(DriverType.ECONOMICAL, rng)
    premium = sample_driver_profile(DriverType.PREMIUM, rng)
    assert economical.price_sensitivity > premium.price_sensitivity
    assert premium.rating_sensitivity > economical.rating_sensitivity


async def _register(email: str) -> uuid.UUID:
    async with async_session_factory() as db:
        user, _ = await register_user(
            db, RegisterRequest(email=email, password="correcthorsebattery", display_name="Owner")
        )
        return user.id


async def _seed_road_graph(*point_pairs: tuple[float, float]) -> None:
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
                        distance_km=8.0,
                        max_speed_kmh=60.0,
                        road_type="local",
                    ),
                    RoadEdge(
                        from_node_id=b.id,
                        to_node_id=a.id,
                        distance_km=8.0,
                        max_speed_kmh=60.0,
                        road_type="local",
                    ),
                ]
            )
        await db.commit()


async def _setup_running_game_with_owned_station(name: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with async_session_factory() as db:
        db.add(
            StationTemplate(
                name=f"{name} Station",
                latitude=56.02,
                longitude=47.02,
                base_price="2000000.00",
                metadata_json={},
            )
        )
        db.add(Refinery(name=f"{name} Refinery", latitude=56.05, longitude=47.05))
        await db.commit()

    await _seed_road_graph(
        (56.00, 47.00), (56.01, 47.01), (56.02, 47.02), (56.03, 47.03), (56.04, 47.04)
    )

    creator_id = await _register(f"{name.lower()}@example.com")
    async with async_session_factory() as db:
        game = await create_game(db, creator_id, CreateGameRequest(name=name))
        game_id = game.id
    async with async_session_factory() as db:
        await start_game(db, game_id, creator_id)
    async with async_session_factory() as db:
        stations = await station_service.list_game_stations(db, game_id)
        station_id = stations[0].id
    async with async_session_factory() as db:
        await station_service.purchase_station(db, game_id, station_id, creator_id)

    return game_id, station_id


async def test_spawn_vehicles_for_game_respects_elapsed_time_and_cap(
    db_session: AsyncSession,
) -> None:
    game_id, _station_id = await _setup_running_game_with_owned_station("VehicleSpawn")

    vehicles_module._last_spawn_check.pop(game_id, None)
    vehicles_module._spawn_accumulator.pop(game_id, None)

    async with async_session_factory() as db:
        first_call = await spawn_vehicles_for_game(db, game_id, rng=random.Random(1))
    assert first_call == []

    vehicles_module._last_spawn_check[game_id] = datetime.now(UTC) - timedelta(minutes=1)

    async with async_session_factory() as db:
        spawned = await spawn_vehicles_for_game(db, game_id, rng=random.Random(1))

    assert len(spawned) > 0

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        settings = GameSettings.model_validate(game.settings_json)
        rows = (await db.execute(select(Vehicle))).scalars().all()

    assert len(rows) == len(spawned)
    assert len(rows) <= settings.max_active_vehicles
    for vehicle in rows:
        assert "points" in vehicle.route_json
        assert vehicle.tank_capacity_liters > Decimal("0")
        assert vehicle.fuel_liters >= Decimal("0")


async def test_spawn_vehicles_for_game_caps_at_max_active_vehicles(
    db_session: AsyncSession,
) -> None:
    game_id, _station_id = await _setup_running_game_with_owned_station("VehicleCap")

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        settings_json = dict(game.settings_json)
        settings_json["max_active_vehicles"] = 3
        game.settings_json = settings_json
        await db.commit()

    vehicles_module._last_spawn_check.pop(game_id, None)
    vehicles_module._spawn_accumulator.pop(game_id, None)

    async with async_session_factory() as db:
        await spawn_vehicles_for_game(db, game_id, rng=random.Random(2))
    vehicles_module._last_spawn_check[game_id] = datetime.now(UTC) - timedelta(minutes=5)

    async with async_session_factory() as db:
        spawned = await spawn_vehicles_for_game(db, game_id, rng=random.Random(2))

    async with async_session_factory() as db:
        rows = (await db.execute(select(Vehicle))).scalars().all()

    assert len(spawned) <= 3
    assert len(rows) <= 3


async def _bias_vehicle_type_weights(game_id: uuid.UUID, only_type: str) -> None:
    """Zero out every vehicle_types spawn_weight except ``only_type`` so spawn is deterministic."""
    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        settings_json = dict(game.settings_json)
        vehicle_types = {
            name: dict(value) for name, value in settings_json["vehicle_types"].items()
        }
        for name, value in vehicle_types.items():
            value["spawn_weight"] = 1.0 if name == only_type else 0.0
        settings_json["vehicle_types"] = vehicle_types
        game.settings_json = settings_json
        await db.commit()


async def test_spawn_vehicles_for_game_distributes_by_vehicle_type_weight(
    db_session: AsyncSession,
) -> None:
    game_id, _station_id = await _setup_running_game_with_owned_station("VehicleTypeWeight")
    await _bias_vehicle_type_weights(game_id, "motorcycle")

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        settings_json = dict(game.settings_json)
        settings_json["max_active_vehicles"] = 50
        game.settings_json = settings_json
        await db.commit()

    vehicles_module._last_spawn_check[game_id] = datetime.now(UTC) - timedelta(minutes=5)
    async with async_session_factory() as db:
        spawned = await spawn_vehicles_for_game(db, game_id, rng=random.Random(3))
    assert len(spawned) > 0

    async with async_session_factory() as db:
        rows = (await db.execute(select(Vehicle))).scalars().all()
    assert rows
    assert all(vehicle.vehicle_type.value == "motorcycle" for vehicle in rows)


async def test_spawn_vehicles_for_game_cargo_truck_only_buys_diesel(
    db_session: AsyncSession,
) -> None:
    game_id, _station_id = await _setup_running_game_with_owned_station("VehicleCargoTruck")
    await _bias_vehicle_type_weights(game_id, "cargo_truck")

    vehicles_module._last_spawn_check[game_id] = datetime.now(UTC) - timedelta(minutes=5)
    async with async_session_factory() as db:
        spawned = await spawn_vehicles_for_game(db, game_id, rng=random.Random(4))
    assert len(spawned) > 0

    async with async_session_factory() as db:
        rows = (await db.execute(select(Vehicle))).scalars().all()
    assert rows
    assert all(vehicle.vehicle_type.value == "cargo_truck" for vehicle in rows)
    assert all(vehicle.fuel_type == FuelType.DIESEL for vehicle in rows)


async def test_spawn_vehicles_for_game_trolleybus_never_selects_a_station(
    db_session: AsyncSession,
) -> None:
    game_id, _station_id = await _setup_running_game_with_owned_station("VehicleTrolleybus")
    await _bias_vehicle_type_weights(game_id, "trolleybus")

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        settings_json = dict(game.settings_json)
        settings_json["vehicle_refuel_threshold_ratio"] = 1.0
        game.settings_json = settings_json
        await db.commit()

    vehicles_module._last_spawn_check[game_id] = datetime.now(UTC) - timedelta(minutes=5)
    async with async_session_factory() as db:
        spawned = await spawn_vehicles_for_game(db, game_id, rng=random.Random(5))
    assert len(spawned) > 0

    async with async_session_factory() as db:
        rows = (await db.execute(select(Vehicle))).scalars().all()
    assert rows
    assert all(vehicle.vehicle_type.value == "trolleybus" for vehicle in rows)
    assert all(vehicle.chosen_station_id is None for vehicle in rows)


async def _insert_vehicle(
    db: AsyncSession,
    *,
    game_id: uuid.UUID,
    home_node: routing_service.GraphNode,
    dest_node: routing_service.GraphNode,
    route_json: dict,
    started_at: datetime,
    fuel_liters: Decimal = Decimal("40"),
    chosen_station_id: uuid.UUID | None = None,
) -> Vehicle:
    vehicle = Vehicle(
        game_id=game_id,
        driver_type=DriverType.RANDOM,
        fuel_type=FuelType.AI92,
        home_latitude=home_node.latitude,
        home_longitude=home_node.longitude,
        destination_latitude=dest_node.latitude,
        destination_longitude=dest_node.longitude,
        route_json=route_json,
        route_progress=0.0,
        current_latitude=home_node.latitude,
        current_longitude=home_node.longitude,
        tank_capacity_liters=Decimal("50"),
        fuel_liters=fuel_liters,
        budget=Decimal("100000.00"),
        price_sensitivity=1.0,
        distance_sensitivity=1.0,
        queue_sensitivity=1.0,
        rating_sensitivity=1.0,
        chosen_station_id=chosen_station_id,
        started_at=started_at,
    )
    db.add(vehicle)
    await db.commit()
    await db.refresh(vehicle)
    return vehicle


async def test_update_vehicles_interpolates_position_mid_route(db_session: AsyncSession) -> None:
    game_id, _station_id = await _setup_running_game_with_owned_station("VehicleDrive")

    async with async_session_factory() as db:
        nodes, edges = await routing_service.load_graph(db)
        home_node = routing_service.find_nearest_node(nodes, 56.00, 47.00)
        dest_node = routing_service.find_nearest_node(nodes, 56.04, 47.04)
        route = routing_service.build_multi_stop_route(nodes, edges, [home_node.id, dest_node.id])
        route_json = routing_service.serialize_multi_stop_route(route, [0])
        vehicle = await _insert_vehicle(
            db,
            game_id=game_id,
            home_node=home_node,
            dest_node=dest_node,
            route_json=route_json,
            started_at=datetime.now(UTC) - timedelta(minutes=16),
        )
        vehicle_id = vehicle.id

    async with async_session_factory() as db:
        result = await update_vehicles_for_game(db, game_id)

    assert vehicle_id in result.updated_vehicle_ids
    assert vehicle_id not in result.arrived_vehicle_ids

    async with async_session_factory() as db:
        vehicle = await db.get(Vehicle, vehicle_id)
        assert vehicle is not None
        assert 0.3 < vehicle.route_progress < 0.7
        assert home_node.latitude < vehicle.current_latitude < dest_node.latitude


async def test_update_vehicles_removes_vehicle_on_arrival(db_session: AsyncSession) -> None:
    game_id, _station_id = await _setup_running_game_with_owned_station("VehicleArrive")

    async with async_session_factory() as db:
        nodes, edges = await routing_service.load_graph(db)
        home_node = routing_service.find_nearest_node(nodes, 56.00, 47.00)
        dest_node = routing_service.find_nearest_node(nodes, 56.04, 47.04)
        route = routing_service.build_multi_stop_route(nodes, edges, [home_node.id, dest_node.id])
        route_json = routing_service.serialize_multi_stop_route(route, [0])
        vehicle = await _insert_vehicle(
            db,
            game_id=game_id,
            home_node=home_node,
            dest_node=dest_node,
            route_json=route_json,
            started_at=datetime.now(UTC) - timedelta(minutes=100),
        )
        vehicle_id = vehicle.id

    async with async_session_factory() as db:
        result = await update_vehicles_for_game(db, game_id)

    assert vehicle_id in result.arrived_vehicle_ids

    async with async_session_factory() as db:
        assert await db.get(Vehicle, vehicle_id) is None


async def _build_route_via_station(
    db: AsyncSession,
) -> tuple[routing_service.GraphNode, routing_service.GraphNode, routing_service.GraphNode, dict]:
    nodes, edges = await routing_service.load_graph(db)
    home_node = routing_service.find_nearest_node(nodes, 56.00, 47.00)
    station_node = routing_service.find_nearest_node(nodes, 56.02, 47.02)
    dest_node = routing_service.find_nearest_node(nodes, 56.04, 47.04)
    route = routing_service.build_multi_stop_route(
        nodes, edges, [home_node.id, station_node.id, dest_node.id]
    )
    positions = list(range(len(route.stop_point_indices)))
    route_json = routing_service.serialize_multi_stop_route(route, positions)
    return home_node, station_node, dest_node, route_json


async def test_update_vehicles_queues_then_purchases_fuel_at_station(
    db_session: AsyncSession,
) -> None:
    game_id, station_id = await _setup_running_game_with_owned_station("VehicleBuy")

    async with async_session_factory() as db:
        home_node, _station_node, dest_node, route_json = await _build_route_via_station(db)
        vehicle = await _insert_vehicle(
            db,
            game_id=game_id,
            home_node=home_node,
            dest_node=dest_node,
            route_json=route_json,
            started_at=datetime.now(UTC) - timedelta(minutes=16),
            fuel_liters=Decimal("5"),
            chosen_station_id=station_id,
        )
        vehicle_id = vehicle.id

    async with async_session_factory() as db:
        result = await update_vehicles_for_game(db, game_id)
    assert vehicle_id in result.updated_vehicle_ids
    assert result.purchases == []

    async with async_session_factory() as db:
        vehicle = await db.get(Vehicle, vehicle_id)
        assert vehicle is not None
        assert vehicle.status == VehicleStatus.REFUELING
        assert vehicle.station_departure_at is not None
        station = await db.get(GameStation, station_id)
        assert station is not None
        assert station.queue_length == 1

    async with async_session_factory() as db:
        vehicle = await db.get(Vehicle, vehicle_id)
        assert vehicle is not None
        vehicle.station_departure_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

    async with async_session_factory() as db:
        result = await update_vehicles_for_game(db, game_id)

    assert len(result.purchases) == 1
    purchase = result.purchases[0]
    assert purchase.vehicle_id == vehicle_id
    assert purchase.liters > Decimal("0")

    async with async_session_factory() as db:
        vehicle = await db.get(Vehicle, vehicle_id)
        assert vehicle is not None
        assert vehicle.status == VehicleStatus.DRIVING
        assert vehicle.chosen_station_id is None
        assert vehicle.fuel_liters > Decimal("5")

        station = await db.get(GameStation, station_id)
        assert station is not None
        assert station.queue_length == 0

        station_fuel = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        assert station_fuel.current_liters < Decimal("5000")

        sales = (
            (await db.execute(select(FuelSale).where(FuelSale.station_id == station_id)))
            .scalars()
            .all()
        )
        assert len(sales) == 1

        player = (
            (await db.execute(select(GamePlayer).where(GamePlayer.game_id == game_id)))
            .scalars()
            .first()
        )
        assert player is not None
        assert player.balance > Decimal("0")


async def test_update_vehicles_skips_purchase_on_stockout_and_lowers_rating(
    db_session: AsyncSession,
) -> None:
    game_id, station_id = await _setup_running_game_with_owned_station("VehicleStockout")

    async with async_session_factory() as db:
        station_fuel = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        station_fuel.current_liters = Decimal("0")
        await db.commit()

    async with async_session_factory() as db:
        home_node, _station_node, dest_node, route_json = await _build_route_via_station(db)
        vehicle = await _insert_vehicle(
            db,
            game_id=game_id,
            home_node=home_node,
            dest_node=dest_node,
            route_json=route_json,
            started_at=datetime.now(UTC) - timedelta(minutes=16),
            fuel_liters=Decimal("5"),
            chosen_station_id=station_id,
        )
        vehicle_id = vehicle.id

    async with async_session_factory() as db:
        await update_vehicles_for_game(db, game_id)

    async with async_session_factory() as db:
        vehicle = await db.get(Vehicle, vehicle_id)
        assert vehicle is not None
        vehicle.station_departure_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

    async with async_session_factory() as db:
        result = await update_vehicles_for_game(db, game_id)

    assert result.purchases == []

    async with async_session_factory() as db:
        vehicle = await db.get(Vehicle, vehicle_id)
        assert vehicle is not None
        assert vehicle.status == VehicleStatus.DRIVING
        station = await db.get(GameStation, station_id)
        assert station is not None
        assert station.rating < 5.0


def test_compute_station_score_rewards_active_upgrades() -> None:
    settings = GameSettings()
    base = StationCandidate(
        station_id=uuid.uuid4(),
        retail_price=Decimal("50.00"),
        detour_km=1.0,
        queue_length=0,
        rating=4.0,
    )
    boosted = StationCandidate(
        station_id=uuid.uuid4(),
        retail_price=Decimal("50.00"),
        detour_km=1.0,
        queue_length=0,
        rating=4.0,
        upgrade_score=1.0,
        advertising_score=1.0,
        loyalty_score=1.0,
    )
    profile = _profile()

    base_score = compute_station_score(
        base,
        cheapest_available_price=Decimal("50.00"),
        profile=profile,
        settings=settings,
        random_factor=0.0,
    )
    boosted_score = compute_station_score(
        boosted,
        cheapest_available_price=Decimal("50.00"),
        profile=profile,
        settings=settings,
        random_factor=0.0,
    )
    assert boosted_score > base_score


async def _owner_user_id(game_id: uuid.UUID) -> uuid.UUID:
    async with async_session_factory() as db:
        player = (
            await db.execute(select(GamePlayer).where(GamePlayer.game_id == game_id))
        ).scalar_one()
        return player.user_id


async def _activate_upgrade(
    game_id: uuid.UUID, station_id: uuid.UUID, upgrade_type: UpgradeType
) -> None:
    owner_id = await _owner_user_id(game_id)
    async with async_session_factory() as db:
        upgrade = await purchase_upgrade(db, game_id, owner_id, station_id, upgrade_type)
        upgrade_id = upgrade.id
    async with async_session_factory() as db:
        upgrade = await db.get(StationUpgrade, upgrade_id)
        assert upgrade is not None
        upgrade.status = UpgradeStatus.ACTIVE
        await db.commit()


async def test_update_vehicles_applies_shop_ancillary_revenue_on_purchase(
    db_session: AsyncSession,
) -> None:
    game_id, station_id = await _setup_running_game_with_owned_station("VehicleShopUpgrade")
    await _activate_upgrade(game_id, station_id, UpgradeType.SHOP)

    async with async_session_factory() as db:
        home_node, _station_node, dest_node, route_json = await _build_route_via_station(db)
        vehicle = await _insert_vehicle(
            db,
            game_id=game_id,
            home_node=home_node,
            dest_node=dest_node,
            route_json=route_json,
            started_at=datetime.now(UTC) - timedelta(minutes=16),
            fuel_liters=Decimal("5"),
            chosen_station_id=station_id,
        )
        vehicle_id = vehicle.id

    async with async_session_factory() as db:
        await update_vehicles_for_game(db, game_id)

    async with async_session_factory() as db:
        vehicle = await db.get(Vehicle, vehicle_id)
        assert vehicle is not None
        vehicle.station_departure_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

    async with async_session_factory() as db:
        result = await update_vehicles_for_game(db, game_id)

    assert len(result.purchases) == 1
    assert result.purchases[0].ancillary_amount > Decimal("0")

    async with async_session_factory() as db:
        ancillary_transactions = (
            (
                await db.execute(
                    select(FinancialTransaction).where(
                        FinancialTransaction.reference_type == "station_ancillary"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(ancillary_transactions) == 1
        assert ancillary_transactions[0].amount > Decimal("0")


async def test_update_vehicles_food_court_upgrade_increases_dwell_time(
    db_session: AsyncSession,
) -> None:
    game_id, station_id = await _setup_running_game_with_owned_station("VehicleFoodCourt")
    await _activate_upgrade(game_id, station_id, UpgradeType.FOOD_COURT)

    async with async_session_factory() as db:
        home_node, _station_node, dest_node, route_json = await _build_route_via_station(db)
        vehicle = await _insert_vehicle(
            db,
            game_id=game_id,
            home_node=home_node,
            dest_node=dest_node,
            route_json=route_json,
            started_at=datetime.now(UTC) - timedelta(minutes=16),
            fuel_liters=Decimal("5"),
            chosen_station_id=station_id,
        )
        vehicle_id = vehicle.id

    baseline_settings = GameSettings()
    baseline_service_minutes = baseline_settings.vehicle_average_service_minutes

    async with async_session_factory() as db:
        await update_vehicles_for_game(db, game_id)

    async with async_session_factory() as db:
        vehicle = await db.get(Vehicle, vehicle_id)
        assert vehicle is not None
        assert vehicle.status == VehicleStatus.REFUELING
        assert vehicle.station_departure_at is not None
        wait_minutes = (vehicle.station_departure_at - datetime.now(UTC)).total_seconds() / 60.0
        # No queue ahead of this vehicle, so the departure delay is purely the
        # (boosted) service time; food court adds bonus_per_level minutes on top.
        assert wait_minutes > baseline_service_minutes
