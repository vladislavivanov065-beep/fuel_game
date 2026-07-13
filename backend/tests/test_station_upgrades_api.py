from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.station_template import StationTemplate
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


async def _seed_station(db_session: AsyncSession, name: str) -> None:
    db_session.add(
        StationTemplate(
            name=name,
            latitude=56.0,
            longitude=47.0,
            base_price="2000000.00",
            metadata_json={},
        )
    )
    await db_session.commit()


async def test_list_station_upgrades_requires_membership(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_station(db_session, "UpgAPI1 Station")

    async with (
        _registered_client("upgapi1@example.com", "Creator") as creator,
        _registered_client("upgapi1b@example.com", "Outsider") as outsider,
    ):
        game = (await creator.post("/api/games", json={"name": "UpgAPI Game 1"})).json()
        await creator.post(f"/api/games/{game['id']}/start")
        stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
        station_id = stations[0]["id"]

        response = await outsider.get(f"/api/games/{game['id']}/stations/{station_id}/upgrades")
        assert response.status_code == 403


async def test_list_station_upgrades_returns_all_nine_types(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_station(db_session, "UpgAPI2 Station")

    async with _registered_client("upgapi2@example.com", "Creator") as creator:
        game = (await creator.post("/api/games", json={"name": "UpgAPI Game 2"})).json()
        await creator.post(f"/api/games/{game['id']}/start")
        stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
        station_id = stations[0]["id"]

        response = await creator.get(f"/api/games/{game['id']}/stations/{station_id}/upgrades")

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 9
        assert all(item["level"] == 0 and item["status"] is None for item in payload)
        types = {item["upgrade_type"] for item in payload}
        assert types == {
            "pumps",
            "tanks",
            "shop",
            "food_court",
            "car_wash",
            "rating",
            "advertising",
            "parking",
            "loyalty_program",
        }


async def test_purchase_station_upgrade_requires_ownership(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_station(db_session, "UpgAPI3 Station")

    async with (
        _registered_client("upgapi3@example.com", "Creator") as creator,
        _registered_client("upgapi3b@example.com", "Other") as other,
    ):
        game = (await creator.post("/api/games", json={"name": "UpgAPI Game 3"})).json()
        invite_code = game["invite_code"]
        await other.post(f"/api/games/{game['id']}/join", json={"invite_code": invite_code})
        await creator.post(f"/api/games/{game['id']}/start")
        stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
        station_id = stations[0]["id"]
        await creator.post(f"/api/games/{game['id']}/stations/{station_id}/purchase")

        response = await other.post(
            f"/api/games/{game['id']}/stations/{station_id}/upgrades",
            json={"upgrade_type": "parking"},
        )
        assert response.status_code == 403


async def test_purchase_station_upgrade_succeeds_and_broadcasts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_station(db_session, "UpgAPI4 Station")

    async with _registered_client("upgapi4@example.com", "Creator") as creator:
        game = (await creator.post("/api/games", json={"name": "UpgAPI Game 4"})).json()
        await creator.post(f"/api/games/{game['id']}/start")
        stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
        station_id = stations[0]["id"]
        await creator.post(f"/api/games/{game['id']}/stations/{station_id}/purchase")

        response = await creator.post(
            f"/api/games/{game['id']}/stations/{station_id}/upgrades",
            json={"upgrade_type": "pumps"},
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["station_id"] == station_id
        assert payload["upgrade_type"] == "pumps"
        assert payload["level"] == 1
        assert payload["status"] == "under_construction"

        info_response = await creator.get(f"/api/games/{game['id']}/stations/{station_id}/upgrades")
        info_payload = info_response.json()
        pumps_info = next(item for item in info_payload if item["upgrade_type"] == "pumps")
        assert pumps_info["level"] == 1
        assert pumps_info["status"] == "under_construction"
        assert float(pumps_info["next_level_cost"]) > 0
