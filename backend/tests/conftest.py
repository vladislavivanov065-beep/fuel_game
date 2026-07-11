import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.redis import redis_client
from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom
from app.db.models.user import User
from app.db.session import async_session_factory
from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _wipe_database() -> None:
    async with async_session_factory() as db:
        await db.execute(delete(GamePlayer))
        await db.execute(delete(GameRoom))
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
