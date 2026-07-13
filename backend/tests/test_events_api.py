from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _seed_station(db_session: AsyncSession, name: str) -> None:
    db_session.add(
        StationTemplate(
            name=name,
            latitude=56.0,
            longitude=47.0,
            base_price="2000000.00",
            metadata_json={},
        )
    )
    await db_session.commit()


async def test_list_active_events_requires_membership(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_station(db_session, "EvtAPI1 Station")

    async with (
        _registered_client("evtapi1@example.com", "Creator") as creator,
        _registered_client("evtapi1b@example.com", "Outsider") as outsider,
    ):
        game = (await creator.post("/api/games", json={"name": "EvtAPI Game 1"})).json()
        await creator.post(f"/api/games/{game['id']}/start")

        response = await outsider.get(f"/api/games/{game['id']}/events")
        assert response.status_code == 403


async def test_trigger_event_requires_admin(client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed_station(db_session, "EvtAPI2 Station")

    async with (
        _registered_client("evtapi2@example.com", "Creator") as creator,
        _registered_client("evtapi2b@example.com", "Other") as other,
    ):
        game = (await creator.post("/api/games", json={"name": "EvtAPI Game 2"})).json()
        invite_code = game["invite_code"]
        await other.post(f"/api/games/{game['id']}/join", json={"invite_code": invite_code})
        await creator.post(f"/api/games/{game['id']}/start")

        response = await other.post(f"/api/games/{game['id']}/events", json={"event_type": "storm"})
        assert response.status_code == 403


async def test_trigger_event_succeeds_and_appears_in_active_and_history(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_station(db_session, "EvtAPI3 Station")

    async with _registered_client("evtapi3@example.com", "Creator") as creator:
        game = (await creator.post("/api/games", json={"name": "EvtAPI Game 3"})).json()
        await creator.post(f"/api/games/{game['id']}/start")

        response = await creator.post(
            f"/api/games/{game['id']}/events", json={"event_type": "storm"}
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["event_type"] == "storm"
        assert payload["status"] == "active"

        active_response = await creator.get(f"/api/games/{game['id']}/events")
        active_payload = active_response.json()
        assert len(active_payload) == 1
        assert active_payload[0]["id"] == payload["id"]

        history_response = await creator.get(f"/api/games/{game['id']}/events/history")
        history_payload = history_response.json()
        assert len(history_payload) == 1
        assert history_payload[0]["id"] == payload["id"]


async def test_trigger_event_requires_running_game(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_station(db_session, "EvtAPI4 Station")

    async with _registered_client("evtapi4@example.com", "Creator") as creator:
        game = (await creator.post("/api/games", json={"name": "EvtAPI Game 4"})).json()

        response = await creator.post(
            f"/api/games/{game['id']}/events", json={"event_type": "storm"}
        )
        assert response.status_code == 409
