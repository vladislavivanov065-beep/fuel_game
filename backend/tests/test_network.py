import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.services.auth_service import register_user
from app.services.game_service import (
    NetworkNameTakenError,
    NotAGameMemberError,
    create_game,
    get_network,
    join_game,
    set_network,
)


async def test_set_network_updates_name_and_color(db_session: AsyncSession) -> None:
    user, _ = await register_user(
        db_session,
        RegisterRequest(
            email="net1@example.com", password="correcthorsebattery", display_name="P1"
        ),
    )
    game = await create_game(db_session, user.id, CreateGameRequest(name="Network Test"))

    player = await set_network(db_session, game.id, user.id, "Rocket Fuel", "#ff0000")

    assert player.network_name == "Rocket Fuel"
    assert player.network_color == "#ff0000"

    fetched = await get_network(db_session, game.id, user.id)
    assert fetched.network_name == "Rocket Fuel"


async def test_set_network_rejects_non_member(db_session: AsyncSession) -> None:
    user, _ = await register_user(
        db_session,
        RegisterRequest(
            email="net2@example.com", password="correcthorsebattery", display_name="P2"
        ),
    )
    game = await create_game(db_session, user.id, CreateGameRequest(name="Network Test 2"))

    outsider, _ = await register_user(
        db_session,
        RegisterRequest(
            email="outsider_net@example.com", password="correcthorsebattery", display_name="Out"
        ),
    )

    with pytest.raises(NotAGameMemberError):
        await set_network(db_session, game.id, outsider.id, "Name", "#00ff00")


async def test_set_network_rejects_duplicate_name_within_game() -> None:
    async with async_session_factory() as db:
        creator, _ = await register_user(
            db,
            RegisterRequest(
                email="net3@example.com", password="correcthorsebattery", display_name="C"
            ),
        )
        game = await create_game(db, creator.id, CreateGameRequest(name="Network Test 3"))

    async with async_session_factory() as db:
        other, _ = await register_user(
            db,
            RegisterRequest(
                email="net3b@example.com", password="correcthorsebattery", display_name="O"
            ),
        )

    async with async_session_factory() as db:
        await join_game(db, game.id, other.id, game.invite_code)

    async with async_session_factory() as db:
        await set_network(db, game.id, creator.id, "SharedName", "#111111")

    async with async_session_factory() as db:
        with pytest.raises(NetworkNameTakenError):
            await set_network(db, game.id, other.id, "SharedName", "#222222")
