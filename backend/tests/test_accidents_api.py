from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.road_accident import AccidentSeverity, RoadAccident
from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode
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


async def _seed_edge(db_session: AsyncSession) -> str:
    node_a = RoadNode(latitude=56.0, longitude=47.0)
    node_b = RoadNode(latitude=56.01, longitude=47.0)
    db_session.add_all([node_a, node_b])
    await db_session.flush()
    edge = RoadEdge(
        from_node_id=node_a.id,
        to_node_id=node_b.id,
        distance_km=1.0,
        max_speed_kmh=60.0,
        road_type="local",
    )
    db_session.add(edge)
    await db_session.commit()
    await db_session.refresh(edge)
    return str(edge.id)


async def test_list_active_accidents_requires_membership(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    async with (
        _registered_client("accapi1@example.com", "Creator") as creator,
        _registered_client("accapi1b@example.com", "Outsider") as outsider,
    ):
        game = (await creator.post("/api/games", json={"name": "AccAPI Game 1"})).json()
        await creator.post(f"/api/games/{game['id']}/start")

        response = await outsider.get(f"/api/games/{game['id']}/accidents")
        assert response.status_code == 403


async def test_list_active_accidents_returns_only_unexpired_ones(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    edge_id = await _seed_edge(db_session)

    async with _registered_client("accapi2@example.com", "Creator") as creator:
        game = (await creator.post("/api/games", json={"name": "AccAPI Game 2"})).json()
        await creator.post(f"/api/games/{game['id']}/start")

        db_session.add(
            RoadAccident(
                game_id=game["id"],
                road_edge_id=edge_id,
                severity=AccidentSeverity.MAJOR,
                previous_traffic_coefficient=1.0,
                ends_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
        db_session.add(
            RoadAccident(
                game_id=game["id"],
                road_edge_id=edge_id,
                severity=AccidentSeverity.MINOR,
                previous_traffic_coefficient=1.0,
                ends_at=datetime.now(UTC) - timedelta(minutes=5),
            )
        )
        await db_session.commit()

        response = await creator.get(f"/api/games/{game['id']}/accidents")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["severity"] == "major"
        assert payload[0]["road_edge_id"] == edge_id
