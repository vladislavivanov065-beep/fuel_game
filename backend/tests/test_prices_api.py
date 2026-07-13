from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.station_fuel import StationFuel
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


async def _create_and_start_game(
    client: AsyncClient, db_session: AsyncSession, name: str = "Price Test"
) -> tuple[dict, str]:
    db_session.add(
        StationTemplate(
            name=f"{name} Station",
            latitude=56.0,
            longitude=47.0,
            base_price="3000000.00",
            metadata_json={},
        )
    )
    await db_session.commit()

    game_response = await client.post("/api/games", json={"name": name})
    assert game_response.status_code == 201
    game = game_response.json()

    await client.post(f"/api/games/{game['id']}/start")

    stations = (await client.get(f"/api/games/{game['id']}/stations")).json()
    station_id = stations[0]["id"]
    return game, station_id


async def test_set_station_price_requires_ownership(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    async with (
        _registered_client("price1@example.com", "Creator") as creator,
        _registered_client("price1b@example.com", "Other") as other,
    ):
        game, station_id = await _create_and_start_game(creator, db_session, "Price1")
        await other.post(f"/api/games/{game['id']}/join", json={"invite_code": game["invite_code"]})

        response = await other.patch(
            f"/api/games/{game['id']}/stations/{station_id}/prices",
            json={"fuel_type": "ai92", "retail_price": "60.00"},
        )

        assert response.status_code == 403


async def test_set_station_price_succeeds_for_owner(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    async with _registered_client("price2@example.com", "Creator") as creator:
        game, station_id = await _create_and_start_game(creator, db_session, "Price2")
        await creator.post(f"/api/games/{game['id']}/stations/{station_id}/purchase")

        response = await creator.patch(
            f"/api/games/{game['id']}/stations/{station_id}/prices",
            json={"fuel_type": "ai92", "retail_price": "62.50"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["fuel_type"] == "ai92"
        assert body["retail_price"] == "62.50"
        assert body["price_updated_at"] is not None


async def test_set_station_price_rejects_out_of_bounds(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    async with _registered_client("price3@example.com", "Creator") as creator:
        game, station_id = await _create_and_start_game(creator, db_session, "Price3")
        await creator.post(f"/api/games/{game['id']}/stations/{station_id}/purchase")

        response = await creator.patch(
            f"/api/games/{game['id']}/stations/{station_id}/prices",
            json={"fuel_type": "ai92", "retail_price": "999.00"},
        )

        assert response.status_code == 422


async def test_set_station_price_rejects_rapid_repeat_change(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    async with _registered_client("price4@example.com", "Creator") as creator:
        game, station_id = await _create_and_start_game(creator, db_session, "Price4")
        await creator.post(f"/api/games/{game['id']}/stations/{station_id}/purchase")

        first = await creator.patch(
            f"/api/games/{game['id']}/stations/{station_id}/prices",
            json={"fuel_type": "ai92", "retail_price": "56.00"},
        )
        assert first.status_code == 200

        second = await creator.patch(
            f"/api/games/{game['id']}/stations/{station_id}/prices",
            json={"fuel_type": "ai92", "retail_price": "57.00"},
        )

        assert second.status_code == 429


async def test_set_station_price_rejects_below_cost(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    async with _registered_client("price5@example.com", "Creator") as creator:
        game, station_id = await _create_and_start_game(creator, db_session, "Price5")
        await creator.post(f"/api/games/{game['id']}/stations/{station_id}/purchase")

        await db_session.execute(
            update(StationFuel)
            .where(StationFuel.game_station_id == station_id, StationFuel.fuel_type == "ai92")
            .values(average_purchase_price="70.00")
        )
        await db_session.commit()

        response = await creator.patch(
            f"/api/games/{game['id']}/stations/{station_id}/prices",
            json={"fuel_type": "ai92", "retail_price": "50.00"},
        )

        assert response.status_code == 409


async def test_set_network_price_updates_all_owned_stations(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    async with _registered_client("price6@example.com", "Creator") as creator:
        db_session.add_all(
            [
                StationTemplate(
                    name="Price6 Station A",
                    latitude=56.0,
                    longitude=47.0,
                    base_price="2000000.00",
                    metadata_json={},
                ),
                StationTemplate(
                    name="Price6 Station B",
                    latitude=56.1,
                    longitude=47.1,
                    base_price="2000000.00",
                    metadata_json={},
                ),
            ]
        )
        await db_session.commit()

        game_response = await creator.post("/api/games", json={"name": "Price6"})
        game = game_response.json()
        await creator.post(f"/api/games/{game['id']}/start")

        stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
        for station in stations:
            await creator.post(f"/api/games/{game['id']}/stations/{station['id']}/purchase")

        response = await creator.patch(
            f"/api/games/{game['id']}/network/prices",
            json={"fuel_type": "ai95", "retail_price": "63.00"},
        )

        assert response.status_code == 200
        assert response.json()["updated_stations"] == len(stations)

        updated_stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
        for station in updated_stations:
            ai95_fuel = next(f for f in station["fuels"] if f["fuel_type"] == "ai95")
            assert ai95_fuel["retail_price"] == "63.00"
