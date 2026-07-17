import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import reset_rate_limits
from app.db.models.financial_transaction import FinancialTransaction
from app.db.models.fuel_order import FuelOrder
from app.db.models.fuel_order_stop import FuelOrderStop
from app.db.models.fuel_sale import FuelSale
from app.db.models.game_event import GameEvent
from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom
from app.db.models.game_station import GameStation
from app.db.models.refinery import Refinery
from app.db.models.refinery_fuel import RefineryFuel
from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode
from app.db.models.session import Session
from app.db.models.station_fuel import StationFuel
from app.db.models.station_template import StationTemplate
from app.db.models.station_upgrade import StationUpgrade
from app.db.models.trade_offer import TradeOffer
from app.db.models.truck import Truck
from app.db.models.user import User
from app.db.models.vehicle import Vehicle
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
        await db.execute(delete(Vehicle))
        await db.execute(delete(Truck))
        await db.execute(delete(FuelOrderStop))
        await db.execute(delete(FuelOrder))
        await db.execute(delete(FuelSale))
        await db.execute(delete(StationFuel))
        await db.execute(delete(StationUpgrade))
        await db.execute(delete(TradeOffer))
        await db.execute(delete(GameStation))
        await db.execute(delete(RefineryFuel))
        await db.execute(delete(GamePlayer))
        await db.execute(delete(GameEvent))
        await db.execute(delete(GameRoom))
        await db.execute(delete(StationTemplate))
        await db.execute(delete(Refinery))
        await db.execute(delete(RoadEdge))
        await db.execute(delete(RoadNode))
        await db.execute(delete(Session))
        await db.execute(delete(User))
        await db.commit()


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    reset_rate_limits()
    await _wipe_database()
    yield
    await _wipe_database()
