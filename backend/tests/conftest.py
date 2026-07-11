import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client
from app.db.models.financial_transaction import FinancialTransaction
from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom
from app.db.models.game_station import GameStation
from app.db.models.refinery import Refinery
from app.db.models.station_fuel import StationFuel
from app.db.models.station_template import StationTemplate
from app.db.models.user import User
from app.db.session import async_session_factory
from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


async def _wipe_database() -> None:
    async with async_session_factory() as db:
        await db.execute(delete(FinancialTransaction))
        await db.execute(delete(StationFuel))
        await db.execute(delete(GameStation))
        await db.execute(delete(GamePlayer))
        await db.execute(delete(GameRoom))
        await db.execute(delete(StationTemplate))
        await db.execute(delete(Refinery))
        await db.execute(delete(User))
        await db.commit()

    keys = await redis_client.keys("session:*")
    keys += await redis_client.keys("rate_limit:*")
    if keys:
        await redis_client.delete(*keys)


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    await _wipe_database()
    yield
    await _wipe_database()
