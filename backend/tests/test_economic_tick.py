from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.financial_transaction import TRANSACTION_TYPE_FUEL_SALE, FinancialTransaction
from app.db.models.fuel_sale import FuelSale
from app.db.models.game_player import GamePlayer
from app.db.models.game_station import GameStation
from app.db.models.station_fuel import FuelType, StationFuel
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


async def test_economic_tick_sells_fuel_and_credits_owner(db_session: AsyncSession) -> None:
    db_session.add(
        StationTemplate(
            name="Tick Station",
            latitude=56.0,
            longitude=47.0,
            base_price="2000000.00",
            metadata_json={},
        )
    )
    await db_session.commit()

    async with _registered_client("tick1@example.com", "Owner") as creator:
        game_response = await creator.post("/api/games", json={"name": "Tick Game"})
        game = game_response.json()
        await creator.post(f"/api/games/{game['id']}/start")

        stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
        station_id = stations[0]["id"]
        await creator.post(f"/api/games/{game['id']}/stations/{station_id}/purchase")

    game_id = game["id"]

    async with async_session_factory() as tick_session:
        station_before = (
            await tick_session.execute(select(GameStation).where(GameStation.id == station_id))
        ).scalar_one()
        player_before = (
            await tick_session.execute(
                select(GamePlayer).where(GamePlayer.id == station_before.owner_player_id)
            )
        ).scalar_one()
        balance_before = player_before.balance

        fuel_before = (
            await tick_session.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        liters_before = fuel_before.current_liters

        result = await economy.run_economic_tick_for_game(tick_session, game_id)

    assert len(result.station_sales) == 3
    ai92_sale = next(s for s in result.station_sales if s.fuel_type == "ai92")
    assert ai92_sale.liters_sold == Decimal("50.00")

    async with async_session_factory() as verify_session:
        fuel_after = (
            await verify_session.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        assert fuel_after.current_liters == liters_before - Decimal("50.00")

        player_after = (
            await verify_session.execute(
                select(GamePlayer).where(GamePlayer.id == station_before.owner_player_id)
            )
        ).scalar_one()
        assert player_after.balance > balance_before

        sales = (
            (await verify_session.execute(select(FuelSale).where(FuelSale.game_id == game_id)))
            .scalars()
            .all()
        )
        assert len(sales) == 3

        transactions = (
            (
                await verify_session.execute(
                    select(FinancialTransaction).where(
                        FinancialTransaction.game_id == game_id,
                        FinancialTransaction.transaction_type == TRANSACTION_TYPE_FUEL_SALE,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(transactions) == 1
        assert transactions[0].balance_after == player_after.balance


async def test_economic_tick_raises_for_non_running_game(db_session: AsyncSession) -> None:
    db_session.add(
        StationTemplate(
            name="Tick Station 2",
            latitude=56.0,
            longitude=47.0,
            base_price="2000000.00",
            metadata_json={},
        )
    )
    await db_session.commit()

    async with _registered_client("tick2@example.com", "Owner2") as creator:
        game_response = await creator.post("/api/games", json={"name": "Tick Game 2"})
        game = game_response.json()

    async with async_session_factory() as tick_session:
        try:
            await economy.run_economic_tick_for_game(tick_session, game["id"])
            raised = False
        except economy.GameNotRunningError:
            raised = True

    assert raised
