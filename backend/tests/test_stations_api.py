import asyncio
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


async def _create_game(client: AsyncClient, name: str = "Station API Test") -> dict:
    response = await client.post("/api/games", json={"name": name})
    assert response.status_code == 201
    return response.json()


async def test_list_stations_requires_membership(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add(
        StationTemplate(
            name="API Station",
            latitude=56.0,
            longitude=47.0,
            base_price="3000000.00",
            metadata_json={},
        )
    )
    await db_session.commit()

    async with (
        _registered_client("stationapi1@example.com", "Creator") as creator,
        _registered_client("stationapi1b@example.com", "Outsider") as outsider,
    ):
        game = await _create_game(creator)

        response = await outsider.get(f"/api/games/{game['id']}/stations")
        assert response.status_code == 403


async def test_list_stations_after_game_start(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add(
        StationTemplate(
            name="API Station 2",
            latitude=56.0,
            longitude=47.0,
            base_price="3000000.00",
            metadata_json={},
        )
    )
    await db_session.commit()

    async with _registered_client("stationapi2@example.com", "Creator") as creator:
        game = await _create_game(creator)
        await creator.post(f"/api/games/{game['id']}/start")

        response = await creator.get(f"/api/games/{game['id']}/stations")

        assert response.status_code == 200
        stations = response.json()
        assert len(stations) == 1
        assert stations[0]["owner_player_id"] is None
        assert stations[0]["name"] == "API Station 2"


async def test_purchase_station_via_api_succeeds(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add(
        StationTemplate(
            name="API Station 3",
            latitude=56.0,
            longitude=47.0,
            base_price="3000000.00",
            metadata_json={},
        )
    )
    await db_session.commit()

    async with _registered_client("stationapi3@example.com", "Creator") as creator:
        game = await _create_game(creator)
        await creator.post(f"/api/games/{game['id']}/start")
        stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
        station_id = stations[0]["id"]

        response = await creator.post(f"/api/games/{game['id']}/stations/{station_id}/purchase")

        assert response.status_code == 200
        body = response.json()
        assert body["owner_player_id"] is not None
        assert body["owner_display_name"] == "Creator"

        detail = await creator.get(f"/api/games/{game['id']}")
        creator_player = detail.json()["players"][0]
        assert creator_player["balance"] == "2000000.00"


async def test_purchase_station_via_api_conflict_when_already_owned(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add(
        StationTemplate(
            name="API Station 4",
            latitude=56.0,
            longitude=47.0,
            base_price="3000000.00",
            metadata_json={},
        )
    )
    await db_session.commit()

    async with (
        _registered_client("stationapi4@example.com", "Creator") as creator,
        _registered_client("stationapi4b@example.com", "Other") as other,
    ):
        game = await _create_game(creator)
        await other.post(f"/api/games/{game['id']}/join", json={"invite_code": game["invite_code"]})
        await creator.post(f"/api/games/{game['id']}/start")
        stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
        station_id = stations[0]["id"]

        first = await creator.post(f"/api/games/{game['id']}/stations/{station_id}/purchase")
        assert first.status_code == 200

        second = await other.post(f"/api/games/{game['id']}/stations/{station_id}/purchase")
        assert second.status_code == 409


async def test_concurrent_purchase_via_api_only_one_succeeds(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add(
        StationTemplate(
            name="API Station 5",
            latitude=56.0,
            longitude=47.0,
            base_price="3000000.00",
            metadata_json={},
        )
    )
    await db_session.commit()

    async with (
        _registered_client("stationapi5@example.com", "Creator") as creator,
        _registered_client("stationapi5b@example.com", "Other") as other,
    ):
        game = await _create_game(creator)
        await other.post(f"/api/games/{game['id']}/join", json={"invite_code": game["invite_code"]})
        await creator.post(f"/api/games/{game['id']}/start")
        stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
        station_id = stations[0]["id"]

        async def attempt(client_instance: AsyncClient) -> int:
            response = await client_instance.post(
                f"/api/games/{game['id']}/stations/{station_id}/purchase"
            )
            return response.status_code

        results = await asyncio.gather(attempt(creator), attempt(other))

        assert sorted(results) == [200, 409]


async def test_network_set_get_and_conflict(client: AsyncClient) -> None:
    async with (
        _registered_client("networkapi1@example.com", "Creator") as creator,
        _registered_client("networkapi1b@example.com", "Other") as other,
    ):
        game = await _create_game(creator)
        await other.post(f"/api/games/{game['id']}/join", json={"invite_code": game["invite_code"]})

        response = await creator.post(
            f"/api/games/{game['id']}/network",
            json={"network_name": "Rocket Fuel Co", "network_color": "#ff0000"},
        )
        assert response.status_code == 200
        assert response.json()["network_name"] == "Rocket Fuel Co"

        get_response = await creator.get(f"/api/games/{game['id']}/network")
        assert get_response.status_code == 200
        assert get_response.json()["network_color"] == "#ff0000"

        conflict = await other.post(
            f"/api/games/{game['id']}/network",
            json={"network_name": "Rocket Fuel Co", "network_color": "#00ff00"},
        )
        assert conflict.status_code == 409


async def test_network_rejects_invalid_color(client: AsyncClient) -> None:
    async with _registered_client("networkapi2@example.com", "Creator") as creator:
        game = await _create_game(creator)

        response = await creator.post(
            f"/api/games/{game['id']}/network",
            json={"network_name": "Bad Color Co", "network_color": "not-a-color"},
        )

        assert response.status_code == 422
