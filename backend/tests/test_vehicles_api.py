from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.refinery import Refinery
from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode
from app.db.models.station_fuel import FuelType
from app.db.models.station_template import StationTemplate
from app.db.models.vehicle import DriverType, Vehicle
from app.db.session import async_session_factory
from app.main import app
from app.services import routing_service


@asynccontextmanager
async def _registered_client(email: str, display_name: str) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/register",
            json={"email": email, "password": "correcthorsebattery", "display_name": display_name},
        )
        assert response.status_code == 201
        yield client


async def _seed_station_and_road_graph(db_session: AsyncSession, name: str) -> None:
    db_session.add(
        StationTemplate(
            name=f"{name} Station",
            latitude=56.0,
            longitude=47.0,
            base_price="2000000.00",
            metadata_json={},
        )
    )
    db_session.add(Refinery(name=f"{name} Refinery", latitude=56.05, longitude=47.05))
    await db_session.commit()

    async with async_session_factory() as db:
        node_a = RoadNode(latitude=56.05, longitude=47.05)
        node_b = RoadNode(latitude=56.0, longitude=47.0)
        db.add_all([node_a, node_b])
        await db.flush()
        db.add_all(
            [
                RoadEdge(
                    from_node_id=node_a.id,
                    to_node_id=node_b.id,
                    distance_km=10.0,
                    max_speed_kmh=60.0,
                    road_type="local",
                ),
                RoadEdge(
                    from_node_id=node_b.id,
                    to_node_id=node_a.id,
                    distance_km=10.0,
                    max_speed_kmh=60.0,
                    road_type="local",
                ),
            ]
        )
        await db.commit()


async def test_list_vehicles_requires_membership(db_session: AsyncSession) -> None:
    async with (
        _registered_client("veh1@example.com", "Creator") as creator,
        _registered_client("veh1b@example.com", "Other") as other,
    ):
        game_response = await creator.post("/api/games", json={"name": "Vehicle Game 1"})
        game = game_response.json()

        response = await other.get(f"/api/games/{game['id']}/vehicles")

        assert response.status_code == 403


async def test_list_vehicles_returns_active_vehicles_for_the_game(
    db_session: AsyncSession,
) -> None:
    await _seed_station_and_road_graph(db_session, "Veh2")

    async with _registered_client("veh2@example.com", "Creator") as creator:
        game_response = await creator.post("/api/games", json={"name": "Vehicle Game 2"})
        game = game_response.json()
        game_id = game["id"]
        await creator.post(f"/api/games/{game_id}/start")

        async with async_session_factory() as db:
            nodes, edges = await routing_service.load_graph(db)
            home_node = routing_service.find_nearest_node(nodes, 56.05, 47.05)
            dest_node = routing_service.find_nearest_node(nodes, 56.0, 47.0)
            route = routing_service.build_multi_stop_route(
                nodes, edges, [home_node.id, dest_node.id]
            )
            route_json = routing_service.serialize_multi_stop_route(route, [0])

            vehicle = Vehicle(
                game_id=game_id,
                driver_type=DriverType.RANDOM,
                fuel_type=FuelType.AI92,
                home_latitude=home_node.latitude,
                home_longitude=home_node.longitude,
                destination_latitude=dest_node.latitude,
                destination_longitude=dest_node.longitude,
                route_json=route_json,
                route_progress=0.2,
                current_latitude=home_node.latitude,
                current_longitude=home_node.longitude,
                tank_capacity_liters=Decimal("50"),
                fuel_liters=Decimal("30"),
                budget=Decimal("10000.00"),
                price_sensitivity=1.0,
                distance_sensitivity=1.0,
                queue_sensitivity=1.0,
                rating_sensitivity=1.0,
                started_at=datetime.now(UTC),
            )
            db.add(vehicle)
            await db.commit()
            vehicle_id = vehicle.id

        response = await creator.get(f"/api/games/{game_id}/vehicles")

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["id"] == str(vehicle_id)
        assert payload[0]["driver_type"] == "random"
        assert payload[0]["fuel_type"] == "ai92"
        assert payload[0]["status"] == "driving"
        assert len(payload[0]["route_points"]) >= 2
