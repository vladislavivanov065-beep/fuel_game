import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

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


async def _create_game(client: AsyncClient, name: str = "Test Room") -> dict:
    response = await client.post("/api/games", json={"name": name})
    assert response.status_code == 201
    return response.json()


async def test_create_game_returns_lobby_with_creator(client: AsyncClient) -> None:
    async with _registered_client("creator@example.com", "Creator") as creator:
        game = await _create_game(creator)

        assert game["status"] == "lobby"
        assert len(game["invite_code"]) > 0
        assert len(game["players"]) == 1
        assert game["players"][0]["is_admin"] is True
        assert game["players"][0]["display_name"] == "Creator"


async def test_create_game_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/api/games", json={"name": "Nope"})

    assert response.status_code == 401


async def test_list_games_returns_only_member_games(client: AsyncClient) -> None:
    async with (
        _registered_client("creator2@example.com", "Creator") as creator,
        _registered_client("outsider@example.com", "Outsider") as outsider,
    ):
        await _create_game(creator)

        creator_games = (await creator.get("/api/games")).json()
        outsider_games = (await outsider.get("/api/games")).json()

        assert len(creator_games) == 1
        assert outsider_games == []


async def test_resolve_invite_code_returns_preview(client: AsyncClient) -> None:
    async with (
        _registered_client("creator3@example.com", "Creator") as creator,
        _registered_client("joiner3@example.com", "Joiner") as joiner,
    ):
        game = await _create_game(creator)

        response = await joiner.get(f"/api/games/resolve/{game['invite_code']}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == game["id"]
        assert body["player_count"] == 1


async def test_resolve_unknown_invite_code_returns_404(client: AsyncClient) -> None:
    async with _registered_client("creator4@example.com", "Creator") as creator:
        response = await creator.get("/api/games/resolve/NOPE0000")

        assert response.status_code == 404


async def test_get_game_denies_non_member(client: AsyncClient) -> None:
    async with (
        _registered_client("creator5@example.com", "Creator") as creator,
        _registered_client("outsider5@example.com", "Outsider") as outsider,
    ):
        game = await _create_game(creator)

        response = await outsider.get(f"/api/games/{game['id']}")

        assert response.status_code == 403


async def test_join_with_wrong_invite_code_returns_403(client: AsyncClient) -> None:
    async with (
        _registered_client("creator6@example.com", "Creator") as creator,
        _registered_client("joiner6@example.com", "Joiner") as joiner,
    ):
        game = await _create_game(creator)

        response = await joiner.post(
            f"/api/games/{game['id']}/join", json={"invite_code": "WRONGCODE"}
        )

        assert response.status_code == 403


async def test_join_with_correct_invite_code_succeeds(client: AsyncClient) -> None:
    async with (
        _registered_client("creator7@example.com", "Creator") as creator,
        _registered_client("joiner7@example.com", "Joiner") as joiner,
    ):
        game = await _create_game(creator)

        response = await joiner.post(
            f"/api/games/{game['id']}/join", json={"invite_code": game["invite_code"]}
        )

        assert response.status_code == 200
        assert len(response.json()["players"]) == 2


async def test_join_twice_returns_409(client: AsyncClient) -> None:
    async with (
        _registered_client("creator8@example.com", "Creator") as creator,
        _registered_client("joiner8@example.com", "Joiner") as joiner,
    ):
        game = await _create_game(creator)
        await joiner.post(
            f"/api/games/{game['id']}/join", json={"invite_code": game["invite_code"]}
        )

        response = await joiner.post(
            f"/api/games/{game['id']}/join", json={"invite_code": game["invite_code"]}
        )

        assert response.status_code == 409


async def test_concurrent_join_same_user_only_one_succeeds(client: AsyncClient) -> None:
    async with (
        _registered_client("creator9@example.com", "Creator") as creator,
        _registered_client("joiner9@example.com", "Joiner") as joiner,
    ):
        game = await _create_game(creator)

        async def attempt() -> int:
            response = await joiner.post(
                f"/api/games/{game['id']}/join", json={"invite_code": game["invite_code"]}
            )
            return response.status_code

        results = await asyncio.gather(attempt(), attempt())

        assert sorted(results) == [200, 409]


async def test_join_after_start_denied_by_default(client: AsyncClient) -> None:
    async with (
        _registered_client("creator10@example.com", "Creator") as creator,
        _registered_client("joiner10@example.com", "Joiner") as joiner,
    ):
        game = await _create_game(creator)
        await creator.post(f"/api/games/{game['id']}/start")

        response = await joiner.post(
            f"/api/games/{game['id']}/join", json={"invite_code": game["invite_code"]}
        )

        assert response.status_code == 409


async def test_leave_removes_player(client: AsyncClient) -> None:
    async with (
        _registered_client("creator11@example.com", "Creator") as creator,
        _registered_client("joiner11@example.com", "Joiner") as joiner,
    ):
        game = await _create_game(creator)
        await joiner.post(
            f"/api/games/{game['id']}/join", json={"invite_code": game["invite_code"]}
        )

        leave_response = await joiner.post(f"/api/games/{game['id']}/leave")
        assert leave_response.status_code == 204

        detail = (await creator.get(f"/api/games/{game['id']}")).json()
        assert len(detail["players"]) == 1


async def test_leave_as_creator_returns_409(client: AsyncClient) -> None:
    async with _registered_client("creator12@example.com", "Creator") as creator:
        game = await _create_game(creator)

        response = await creator.post(f"/api/games/{game['id']}/leave")

        assert response.status_code == 409


async def test_set_ready_updates_player(client: AsyncClient) -> None:
    async with _registered_client("creator13@example.com", "Creator") as creator:
        game = await _create_game(creator)

        response = await creator.post(f"/api/games/{game['id']}/ready", json={"is_ready": True})

        assert response.status_code == 200
        assert response.json()["is_ready"] is True


async def test_start_by_non_creator_returns_403(client: AsyncClient) -> None:
    async with (
        _registered_client("creator14@example.com", "Creator") as creator,
        _registered_client("joiner14@example.com", "Joiner") as joiner,
    ):
        game = await _create_game(creator)
        await joiner.post(
            f"/api/games/{game['id']}/join", json={"invite_code": game["invite_code"]}
        )

        response = await joiner.post(f"/api/games/{game['id']}/start")

        assert response.status_code == 403


async def test_start_assigns_starting_balance(client: AsyncClient) -> None:
    async with _registered_client("creator15@example.com", "Creator") as creator:
        game = await _create_game(creator)

        response = await creator.post(f"/api/games/{game['id']}/start")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "running"
        assert body["started_at"] is not None
        assert body["players"][0]["balance"] == "5000000.00"


async def test_concurrent_start_only_one_succeeds(client: AsyncClient) -> None:
    async with _registered_client("creator16@example.com", "Creator") as creator:
        game = await _create_game(creator)

        async def attempt() -> int:
            response = await creator.post(f"/api/games/{game['id']}/start")
            return response.status_code

        results = await asyncio.gather(attempt(), attempt())

        assert sorted(results) == [200, 409]
