from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.station_template import StationTemplate
from app.db.session import async_session_factory
from app.main import app
from app.simulation import economy


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


async def test_list_my_transactions_requires_membership(db_session: AsyncSession) -> None:
    async with (
        _registered_client("tx1@example.com", "Creator") as creator,
        _registered_client("tx1b@example.com", "Other") as other,
    ):
        game_response = await creator.post("/api/games", json={"name": "Tx Game"})
        game = game_response.json()

        response = await other.get(f"/api/games/{game['id']}/me/transactions")

        assert response.status_code == 403


async def test_list_my_transactions_returns_fuel_sale_records(db_session: AsyncSession) -> None:
    db_session.add(
        StationTemplate(
            name="Tx Station",
            latitude=56.0,
            longitude=47.0,
            base_price="2000000.00",
            metadata_json={},
        )
    )
    await db_session.commit()

    async with _registered_client("tx2@example.com", "Owner") as creator:
        game_response = await creator.post("/api/games", json={"name": "Tx Game 2"})
        game = game_response.json()
        await creator.post(f"/api/games/{game['id']}/start")

        stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
        station_id = stations[0]["id"]
        await creator.post(f"/api/games/{game['id']}/stations/{station_id}/purchase")

        async with async_session_factory() as tick_session:
            await economy.run_economic_tick_for_game(tick_session, game["id"])

        response = await creator.get(f"/api/games/{game['id']}/me/transactions")

        assert response.status_code == 200
        transactions = response.json()
        assert len(transactions) == 2
        fuel_sale_tx = next(t for t in transactions if t["transaction_type"] == "fuel_sale")
        assert fuel_sale_tx["reference_type"] == "economic_tick"
