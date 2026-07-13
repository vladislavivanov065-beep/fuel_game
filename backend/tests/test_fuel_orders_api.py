from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.refinery import Refinery
from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode
from app.db.models.station_template import StationTemplate
from app.db.session import async_session_factory
from app.main import app


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


async def _seed_station_and_refinery(db_session: AsyncSession, name: str) -> None:
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


async def test_list_refineries_requires_membership(db_session: AsyncSession) -> None:
    async with (
        _registered_client("fo1@example.com", "Creator") as creator,
        _registered_client("fo1b@example.com", "Other") as other,
    ):
        game_response = await creator.post("/api/games", json={"name": "FO Game 1"})
        game = game_response.json()

        response = await other.get(f"/api/games/{game['id']}/refineries")

        assert response.status_code == 403


async def test_list_refineries_returns_stock_after_start(db_session: AsyncSession) -> None:
    await _seed_station_and_refinery(db_session, "FO2")

    async with _registered_client("fo2@example.com", "Creator") as creator:
        game_response = await creator.post("/api/games", json={"name": "FO Game 2"})
        game = game_response.json()
        await creator.post(f"/api/games/{game['id']}/start")

        response = await creator.get(f"/api/games/{game['id']}/refineries")

        assert response.status_code == 200
        refineries = response.json()
        assert len(refineries) == 1
        assert len(refineries[0]["fuels"]) == 3


async def test_create_fuel_order_succeeds_via_api(db_session: AsyncSession) -> None:
    await _seed_station_and_refinery(db_session, "FO3")

    async with _registered_client("fo3@example.com", "Creator") as creator:
        game_response = await creator.post("/api/games", json={"name": "FO Game 3"})
        game = game_response.json()
        await creator.post(f"/api/games/{game['id']}/start")

        stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
        station_id = stations[0]["id"]
        await creator.post(f"/api/games/{game['id']}/stations/{station_id}/purchase")

        refineries = (await creator.get(f"/api/games/{game['id']}/refineries")).json()
        refinery_id = refineries[0]["id"]

        response = await creator.post(
            f"/api/games/{game['id']}/fuel-orders",
            json={
                "refinery_id": refinery_id,
                "stops": [{"station_id": station_id, "fuel_type": "ai92", "liters": "2000"}],
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "in_transit"
        assert len(body["stops"]) == 1
        assert body["stops"][0]["liters"] == "2000.00"

        orders = (await creator.get(f"/api/games/{game['id']}/fuel-orders")).json()
        assert len(orders) == 1
        assert orders[0]["id"] == body["id"]


async def test_create_fuel_order_rejects_non_owner_via_api(db_session: AsyncSession) -> None:
    await _seed_station_and_refinery(db_session, "FO4")

    async with (
        _registered_client("fo4@example.com", "Creator") as creator,
        _registered_client("fo4b@example.com", "Other") as other,
    ):
        game_response = await creator.post("/api/games", json={"name": "FO Game 4"})
        game = game_response.json()
        await other.post(f"/api/games/{game['id']}/join", json={"invite_code": game["invite_code"]})
        await creator.post(f"/api/games/{game['id']}/start")

        stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
        station_id = stations[0]["id"]
        await creator.post(f"/api/games/{game['id']}/stations/{station_id}/purchase")

        refineries = (await creator.get(f"/api/games/{game['id']}/refineries")).json()
        refinery_id = refineries[0]["id"]

        response = await other.post(
            f"/api/games/{game['id']}/fuel-orders",
            json={
                "refinery_id": refinery_id,
                "stops": [{"station_id": station_id, "fuel_type": "ai92", "liters": "1000"}],
            },
        )

        assert response.status_code == 403


async def test_list_my_trucks_requires_membership(db_session: AsyncSession) -> None:
    async with (
        _registered_client("fo5@example.com", "Creator") as creator,
        _registered_client("fo5b@example.com", "Other") as other,
    ):
        game_response = await creator.post("/api/games", json={"name": "FO Game 5"})
        game = game_response.json()

        response = await other.get(f"/api/games/{game['id']}/trucks")

        assert response.status_code == 403


async def test_list_my_trucks_returns_truck_after_order(db_session: AsyncSession) -> None:
    await _seed_station_and_refinery(db_session, "FO6")

    async with _registered_client("fo6@example.com", "Creator") as creator:
        game_response = await creator.post("/api/games", json={"name": "FO Game 6"})
        game = game_response.json()
        await creator.post(f"/api/games/{game['id']}/start")

        stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
        station_id = stations[0]["id"]
        await creator.post(f"/api/games/{game['id']}/stations/{station_id}/purchase")

        refineries = (await creator.get(f"/api/games/{game['id']}/refineries")).json()
        refinery_id = refineries[0]["id"]

        order_response = await creator.post(
            f"/api/games/{game['id']}/fuel-orders",
            json={
                "refinery_id": refinery_id,
                "stops": [{"station_id": station_id, "fuel_type": "ai92", "liters": "2000"}],
            },
        )
        assert order_response.status_code == 201
        order_id = order_response.json()["id"]

        response = await creator.get(f"/api/games/{game['id']}/trucks")

        assert response.status_code == 200
        trucks = response.json()
        assert len(trucks) == 1
        assert trucks[0]["fuel_order_id"] == order_id
        assert trucks[0]["status"] == "en_route"
        assert trucks[0]["route_progress"] == 0.0
        assert trucks[0]["total_distance_km"] > 0
        assert len(trucks[0]["route_points"]) >= 2
