import asyncio

from httpx import AsyncClient, Response

VALID_PASSWORD = "correcthorsebattery"


async def _register(client: AsyncClient, email: str = "alice@example.com") -> Response:
    return await client.post(
        "/api/auth/register",
        json={"email": email, "password": VALID_PASSWORD, "display_name": "Alice"},
    )


async def test_register_returns_created_user(client: AsyncClient) -> None:
    response = await _register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert body["display_name"] == "Alice"
    assert "password" not in body
    assert "password_hash" not in body
    assert "session_id" in response.cookies


async def test_register_sets_httponly_cookie(client: AsyncClient) -> None:
    response = await _register(client)

    set_cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "session_id=" in set_cookie


async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    await _register(client)
    response = await _register(client)

    assert response.status_code == 409


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": "bob@example.com", "password": "short", "display_name": "Bob"},
    )

    assert response.status_code == 422


async def test_register_rejects_invalid_email(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": VALID_PASSWORD, "display_name": "Bob"},
    )

    assert response.status_code == 422


async def test_register_rejects_empty_display_name(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": "bob@example.com", "password": VALID_PASSWORD, "display_name": ""},
    )

    assert response.status_code == 422


async def test_login_with_correct_credentials_succeeds(client: AsyncClient) -> None:
    await _register(client)

    response = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": VALID_PASSWORD},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "alice@example.com"


async def test_login_with_wrong_password_returns_401(client: AsyncClient) -> None:
    await _register(client)

    response = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "wrongpassword"},
    )

    assert response.status_code == 401


async def test_login_with_unknown_email_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": VALID_PASSWORD},
    )

    assert response.status_code == 401


async def test_me_without_session_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/auth/me")

    assert response.status_code == 401


async def test_me_with_valid_session_returns_current_user(client: AsyncClient) -> None:
    await _register(client)

    response = await client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "alice@example.com"


async def test_logout_invalidates_session(client: AsyncClient) -> None:
    await _register(client)

    logout_response = await client.post("/api/auth/logout")
    assert logout_response.status_code == 204

    me_response = await client.get("/api/auth/me")
    assert me_response.status_code == 401


async def test_logout_without_session_is_idempotent(client: AsyncClient) -> None:
    response = await client.post("/api/auth/logout")

    assert response.status_code == 204


async def test_concurrent_registration_same_email_only_one_succeeds(client: AsyncClient) -> None:
    async def attempt() -> int:
        response = await _register(client, email="racer@example.com")
        return response.status_code

    results = await asyncio.gather(attempt(), attempt())

    assert sorted(results) == [201, 409]
