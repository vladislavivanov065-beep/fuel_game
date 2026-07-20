import asyncio
from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.password_reset_token import PasswordResetToken
from app.db.models.user import User
from app.db.session import async_session_factory
from app.main import app

VALID_PASSWORD = "correcthorsebattery"
NEW_PASSWORD = "newcorrecthorsebattery"


async def _register(client: AsyncClient, email: str = "alice@example.com") -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": VALID_PASSWORD, "display_name": "Alice"},
    )
    assert response.status_code == 201


async def _forgot_password(client: AsyncClient, email: str) -> str | None:
    response = await client.post("/api/auth/forgot-password", json={"email": email})
    assert response.status_code == 200
    return response.json()["reset_token"]


async def test_forgot_password_known_email_returns_token(client: AsyncClient) -> None:
    await _register(client, "alice@example.com")

    token = await _forgot_password(client, "alice@example.com")

    assert token
    assert isinstance(token, str)


async def test_forgot_password_unknown_email_returns_200_without_token(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/auth/forgot-password", json={"email": "ghost@example.com"})

    assert response.status_code == 200
    body = response.json()
    assert body["reset_token"] is None
    assert body["message"]


async def test_reset_password_with_valid_token_succeeds(client: AsyncClient) -> None:
    await _register(client, "alice@example.com")
    token = await _forgot_password(client, "alice@example.com")

    reset_response = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert reset_response.status_code == 204

    old_login = await client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": VALID_PASSWORD}
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": NEW_PASSWORD}
    )
    assert new_login.status_code == 200


async def test_reset_password_invalidates_all_sessions(client: AsyncClient) -> None:
    await _register(client, "alice@example.com")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as other_client:
        login_response = await other_client.post(
            "/api/auth/login",
            json={"email": "alice@example.com", "password": VALID_PASSWORD},
        )
        assert login_response.status_code == 200

        token = await _forgot_password(client, "alice@example.com")
        reset_response = await client.post(
            "/api/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
        )
        assert reset_response.status_code == 204

        assert (await client.get("/api/auth/me")).status_code == 401
        assert (await other_client.get("/api/auth/me")).status_code == 401


async def test_reset_password_token_is_single_use(client: AsyncClient) -> None:
    await _register(client, "alice@example.com")
    token = await _forgot_password(client, "alice@example.com")

    first = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert first.status_code == 204

    second = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "anotherpassword123"}
    )
    assert second.status_code == 400


async def test_reset_password_expired_token_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(client, "alice@example.com")

    async with async_session_factory() as db:
        user_row = (await db.execute(select(User))).scalar_one()
        db.add(
            PasswordResetToken(
                token="expired-token",
                user_id=user_row.id,
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        await db.commit()

    response = await client.post(
        "/api/auth/reset-password",
        json={"token": "expired-token", "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 400


async def test_reset_password_invalid_token_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/reset-password",
        json={"token": "not-a-real-token", "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 400


async def test_reset_password_rejects_short_password(client: AsyncClient) -> None:
    await _register(client, "alice@example.com")
    token = await _forgot_password(client, "alice@example.com")

    response = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "short"}
    )
    assert response.status_code == 422


async def test_concurrent_reset_same_token_only_one_succeeds(client: AsyncClient) -> None:
    await _register(client, "alice@example.com")
    token = await _forgot_password(client, "alice@example.com")

    async def attempt() -> int:
        response = await client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": NEW_PASSWORD},
        )
        return response.status_code

    results = await asyncio.gather(attempt(), attempt())

    assert sorted(results) == [204, 400]
