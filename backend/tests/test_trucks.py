import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.fuel_order import FuelOrder, FuelOrderStatus
from app.db.models.fuel_order_stop import FuelOrderStop, FuelOrderStopStatus
from app.db.models.refinery import Refinery
from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode
from app.db.models.station_fuel import FuelType, StationFuel
from app.db.models.station_template import StationTemplate
from app.db.models.truck import Truck, TruckStatus
from app.db.session import async_session_factory
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.services.auth_service import register_user
from app.services.fuel_order_service import FuelOrderStopRequest, create_fuel_order
from app.services.game_service import create_game, start_game
from app.services.station_service import list_game_stations, purchase_station
from app.simulation.trucks import update_trucks_for_game


async def _register(email: str, display_name: str = "Player") -> uuid.UUID:
    async with async_session_factory() as db:
        user, _ = await register_user(
            db,
            RegisterRequest(email=email, password="correcthorsebattery", display_name=display_name),
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


async def _setup_game_with_order(
    name: str, liters: str = "2000"
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Register a creator, seed a station+refinery+road, buy the station, and place an order.

    Returns (game_id, station_id, order_id).
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

        order = await create_fuel_order(
            db,
            game_id,
            creator_id,
            refinery.id,
            [
                FuelOrderStopRequest(
                    station_id=station_id, fuel_type=FuelType.AI92, liters=Decimal(liters)
                )
            ],
        )

    return game_id, station_id, order.id


async def test_update_trucks_interpolates_position_mid_route(db_session: AsyncSession) -> None:
    game_id, station_id, order_id = await _setup_game_with_order("TruckMid")

    async with async_session_factory() as db:
        truck = (
            await db.execute(select(Truck).where(Truck.fuel_order_id == order_id))
        ).scalar_one()
        refinery_lat = truck.route_json["points"][0]["latitude"]
        station_lat = truck.route_json["points"][-1]["latitude"]
        # Single 10km edge refinery->station; place the truck halfway along it
        # (Этап 14.3 replaced elapsed-time movement with per-tick physics).
        await db.execute(
            update(Truck).where(Truck.id == truck.id).values(position_on_edge_m=5000.0)
        )
        await db.commit()

    async with async_session_factory() as db:
        result = await update_trucks_for_game(db, game_id)

    assert len(result.updated_truck_ids) == 1
    assert result.delivered_stops == []

    async with async_session_factory() as db:
        truck_after = await db.get(Truck, truck.id)
        assert truck_after is not None
        assert truck_after.status == TruckStatus.EN_ROUTE
        assert 0.3 < truck_after.route_progress < 0.7
        # Somewhere strictly between the refinery and the station, not at either end.
        assert (
            min(refinery_lat, station_lat)
            < truck_after.current_latitude
            < max(refinery_lat, station_lat)
        )

        stop = (
            await db.execute(select(FuelOrderStop).where(FuelOrderStop.fuel_order_id == order_id))
        ).scalar_one()
        assert stop.status == FuelOrderStopStatus.PENDING

        station_fuel = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        assert station_fuel.reserved_liters == Decimal("2000.00")


async def test_update_trucks_delivers_when_route_is_complete(db_session: AsyncSession) -> None:
    game_id, station_id, order_id = await _setup_game_with_order("TruckDone")

    async with async_session_factory() as db:
        truck = (
            await db.execute(select(Truck).where(Truck.fuel_order_id == order_id))
        ).scalar_one()
        # Single 10km edge; place the truck right at the end so one physics
        # tick's advance crosses the finish line.
        await db.execute(
            update(Truck).where(Truck.id == truck.id).values(position_on_edge_m=9999.99)
        )
        await db.commit()

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
        result = await update_trucks_for_game(db, game_id)

    assert len(result.delivered_stops) == 1
    assert result.delivered_stops[0].station_id == station_id
    assert result.delivered_stops[0].liters == Decimal("2000.00")
    assert result.completed_order_ids == [order_id]

    async with async_session_factory() as db:
        truck_after = await db.get(Truck, truck.id)
        assert truck_after is not None
        assert truck_after.status == TruckStatus.DELIVERED
        assert truck_after.route_progress == 1.0

        order_after = await db.get(FuelOrder, order_id)
        assert order_after is not None
        assert order_after.status == FuelOrderStatus.DELIVERED

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


async def test_update_trucks_reroutes_around_a_closed_road(db_session: AsyncSession) -> None:
    name = "TruckReroute"
    async with async_session_factory() as db:
        db.add(
            StationTemplate(
                name=f"{name} Station",
                latitude=56.02,
                longitude=47.0,
                base_price="2000000.00",
                metadata_json={},
            )
        )
        db.add(Refinery(name=f"{name} Refinery", latitude=56.0, longitude=47.0))
        await db.commit()

    # A diamond: refinery(A) -- mid(B) -- station(C) direct, plus a longer
    # detour A -- B -- D -- C so a closure on B->C still leaves a route.
    async with async_session_factory() as db:
        node_a = RoadNode(latitude=56.0, longitude=47.0)
        node_b = RoadNode(latitude=56.01, longitude=47.0)
        node_c = RoadNode(latitude=56.02, longitude=47.0)
        node_d = RoadNode(latitude=56.015, longitude=47.02)
        db.add_all([node_a, node_b, node_c, node_d])
        await db.flush()

        def _two_way(from_node: RoadNode, to_node: RoadNode, distance_km: float) -> list[RoadEdge]:
            return [
                RoadEdge(
                    from_node_id=from_node.id,
                    to_node_id=to_node.id,
                    distance_km=distance_km,
                    max_speed_kmh=60.0,
                    road_type="local",
                ),
                RoadEdge(
                    from_node_id=to_node.id,
                    to_node_id=from_node.id,
                    distance_km=distance_km,
                    max_speed_kmh=60.0,
                    road_type="local",
                ),
            ]

        db.add_all(_two_way(node_a, node_b, 10.0))
        db.add_all(_two_way(node_b, node_c, 5.0))
        db.add_all(_two_way(node_b, node_d, 8.0))
        db.add_all(_two_way(node_d, node_c, 8.0))
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
        order = await create_fuel_order(
            db,
            game_id,
            creator_id,
            refinery.id,
            [
                FuelOrderStopRequest(
                    station_id=station_id, fuel_type=FuelType.AI92, liters=Decimal("1000")
                )
            ],
        )

    async with async_session_factory() as db:
        truck = (
            await db.execute(select(Truck).where(Truck.fuel_order_id == order.id))
        ).scalar_one()
        original_distance = truck.route_json["total_distance_km"]
        # The shortest path (A-B-C, 15km) is what the truck should have taken.
        assert original_distance == 15.0

    # Close the direct B->C road while the truck is still near the start.
    async with async_session_factory() as db:
        await db.execute(update(RoadEdge).where(RoadEdge.distance_km == 5.0).values(is_closed=True))
        await db.commit()

    async with async_session_factory() as db:
        result = await update_trucks_for_game(db, game_id)

    assert truck.id in result.rerouted_truck_ids

    async with async_session_factory() as db:
        truck_after = await db.get(Truck, truck.id)
        assert truck_after is not None
        assert truck_after.status == TruckStatus.EN_ROUTE
        # The new route must be the longer detour through D (10 + 8 + 8 = 26km).
        assert truck_after.route_json["total_distance_km"] == 26.0

    # Fast-forward past the new (longer) route and confirm delivery still happens:
    # place the truck right at the end of the final edge (D->C, 8km) of the
    # rerouted A-B-D-C path.
    async with async_session_factory() as db:
        truck_after = await db.get(Truck, truck.id)
        assert truck_after is not None
        last_index = len(truck_after.route_json["points"]) - 1
        await db.execute(
            update(Truck)
            .where(Truck.id == truck.id)
            .values(route_edge_index=last_index, position_on_edge_m=7999.99)
        )
        await db.commit()

    async with async_session_factory() as db:
        final_result = await update_trucks_for_game(db, game_id)

    assert len(final_result.delivered_stops) == 1
    assert final_result.delivered_stops[0].station_id == station_id
