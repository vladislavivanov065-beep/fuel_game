import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.financial_transaction import FinancialTransaction
from app.db.models.game_event import EventStatus, EventType, GameEvent
from app.db.models.refinery import Refinery
from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode
from app.db.models.station_fuel import FuelType
from app.db.models.station_template import StationTemplate
from app.db.models.vehicle import DriverType, Vehicle
from app.db.session import async_session_factory
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.services import routing_service
from app.services.auth_service import register_user
from app.services.event_service import AttractivenessBonus, Region
from app.services.fuel_order_service import FuelOrderStopRequest, create_fuel_order
from app.services.game_service import create_game, start_game
from app.services.station_service import list_game_stations, purchase_station
from app.simulation import vehicles as vehicles_module
from app.simulation.vehicles import (
    _event_attractiveness_bonus,
    spawn_vehicles_for_game,
    update_vehicles_for_game,
)


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

    await _seed_road_graph(
        (56.05, 47.05), (56.04, 47.04), (56.03, 47.03), (56.02, 47.02), (56.01, 47.01), (56.0, 47.0)
    )

    creator_id = await _register(f"{name.lower()}@example.com")
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


async def _add_event(
    game_id: uuid.UUID, event_type: EventType, modifiers_json: dict[str, object]
) -> None:
    async with async_session_factory() as db:
        db.add(
            GameEvent(
                game_id=game_id,
                event_type=event_type,
                status=EventStatus.ACTIVE,
                region_json=None,
                modifiers_json=modifiers_json,
                started_at=datetime.now(UTC),
                ends_at=datetime.now(UTC) + timedelta(minutes=10),
            )
        )
        await db.commit()


async def test_load_graph_scales_traffic_coefficient_in_memory(db_session: AsyncSession) -> None:
    async with async_session_factory() as db:
        node_a = RoadNode(latitude=56.0, longitude=47.0)
        node_b = RoadNode(latitude=56.01, longitude=47.01)
        db.add_all([node_a, node_b])
        await db.flush()
        edge = RoadEdge(
            from_node_id=node_a.id,
            to_node_id=node_b.id,
            distance_km=5.0,
            max_speed_kmh=60.0,
            road_type="local",
            traffic_coefficient=1.0,
        )
        db.add(edge)
        await db.commit()
        edge_id = edge.id

    async with async_session_factory() as db:
        _nodes, edges = await routing_service.load_graph(db, traffic_multiplier=1.5)

    scaled_edge = next(e for e in edges if e.id == edge_id)
    assert scaled_edge.traffic_coefficient == 1.5

    async with async_session_factory() as db:
        stored_edge = await db.get(RoadEdge, edge_id)
        assert stored_edge is not None
        assert stored_edge.traffic_coefficient == 1.0


async def test_create_fuel_order_applies_refinery_price_multiplier(
    db_session: AsyncSession,
) -> None:
    game_id, creator_id, station_id, refinery_id = await _setup_game("EventCrisis")
    await _add_event(game_id, EventType.ECONOMIC_CRISIS, {"refinery_price_multiplier": 2.0})

    async with async_session_factory() as db:
        order = await create_fuel_order(
            db,
            game_id,
            creator_id,
            refinery_id,
            [
                FuelOrderStopRequest(
                    station_id=station_id, fuel_type=FuelType.AI92, liters=Decimal("1000")
                )
            ],
        )

    default_refinery_price = Decimal("42.00")
    expected_fuel_cost = default_refinery_price * 2 * Decimal("1000")
    assert order.total_cost >= expected_fuel_cost


async def test_spawn_vehicles_respects_vehicle_spawn_multiplier(db_session: AsyncSession) -> None:
    game_id, _creator_id, _station_id, _refinery_id = await _setup_game("EventFuelRiot")
    await _add_event(game_id, EventType.FUEL_RIOT, {"vehicle_spawn_multiplier": 5.0})

    vehicles_module._last_spawn_check.pop(game_id, None)
    vehicles_module._spawn_accumulator.pop(game_id, None)

    async with async_session_factory() as db:
        await spawn_vehicles_for_game(db, game_id, rng=random.Random(1))
    vehicles_module._last_spawn_check[game_id] = datetime.now(UTC) - timedelta(minutes=1)

    async with async_session_factory() as db:
        spawned = await spawn_vehicles_for_game(db, game_id, rng=random.Random(1))

    # Default vehicle_spawn_per_minute is 20; a 5x event multiplier over one
    # minute should push the spawn count well past the un-boosted baseline.
    assert len(spawned) > 20


def test_event_attractiveness_bonus_requires_region_and_upgrade_gate() -> None:
    class _FakeTemplate:
        latitude = 56.0
        longitude = 47.0

    class _FakeStation:
        station_template = _FakeTemplate()

    in_region_no_gate = AttractivenessBonus(
        bonus=1.0, region=Region(56.0, 47.0, 10.0), required_upgrade_types=[]
    )
    out_of_region = AttractivenessBonus(
        bonus=1.0, region=Region(60.0, 50.0, 1.0), required_upgrade_types=[]
    )
    gated_missing = AttractivenessBonus(bonus=1.0, region=None, required_upgrade_types=["parking"])

    total = _event_attractiveness_bonus(
        station=_FakeStation(),  # type: ignore[arg-type]
        upgrade_levels={},
        bonuses=[in_region_no_gate, out_of_region, gated_missing],
    )
    assert total == 1.0


async def test_apply_ancillary_revenue_scales_with_event_multiplier(
    db_session: AsyncSession,
) -> None:
    game_id, creator_id, station_id, _refinery_id = await _setup_game("EventAncillary")

    from app.db.models.station_upgrade import StationUpgrade, UpgradeStatus, UpgradeType
    from app.services.station_upgrade_service import purchase_upgrade

    async with async_session_factory() as db:
        upgrade = await purchase_upgrade(db, game_id, creator_id, station_id, UpgradeType.SHOP)
        upgrade_id = upgrade.id
    async with async_session_factory() as db:
        upgrade = await db.get(StationUpgrade, upgrade_id)
        assert upgrade is not None
        upgrade.status = UpgradeStatus.ACTIVE
        await db.commit()

    await _add_event(game_id, EventType.ECONOMIC_CRISIS, {"ancillary_revenue_multiplier": 0.0})

    async with async_session_factory() as db:
        nodes, edges = await routing_service.load_graph(db)
        home_node = routing_service.find_nearest_node(nodes, 56.05, 47.05)
        station_node = routing_service.find_nearest_node(nodes, 56.03, 47.03)
        dest_node = routing_service.find_nearest_node(nodes, 56.0, 47.0)
        route = routing_service.build_multi_stop_route(
            nodes, edges, [home_node.id, station_node.id, dest_node.id]
        )
        route_json = routing_service.serialize_multi_stop_route(route, [0, 1])

        # Place the vehicle right at the end of the edge leading to the station stop
        # so a single physics tick crosses into it (Этап 14.3 replaced elapsed-time
        # based movement with a per-tick car-following simulation).
        stop_point_index = route_json["stops"][0]["point_index"]
        points = route_json["points"]
        edge_length_m = (
            points[stop_point_index]["cumulative_km"]
            - points[stop_point_index - 1]["cumulative_km"]
        ) * 1000.0

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
            route_edge_index=stop_point_index,
            current_edge_id=uuid.UUID(points[stop_point_index]["edge_id"]),
            position_on_edge_m=max(0.0, edge_length_m - 0.01),
            velocity_kmh=0.0,
            tank_capacity_liters=Decimal("50"),
            fuel_liters=Decimal("5"),
            budget=Decimal("100000.00"),
            price_sensitivity=1.0,
            distance_sensitivity=1.0,
            queue_sensitivity=1.0,
            rating_sensitivity=1.0,
            chosen_station_id=station_id,
            started_at=datetime.now(UTC),
        )
        db.add(vehicle)
        await db.commit()
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
    assert result.purchases[0].ancillary_amount == Decimal("0")

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
        assert len(ancillary_transactions) == 0
