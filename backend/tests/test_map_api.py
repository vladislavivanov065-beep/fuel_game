from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.refinery import Refinery
from app.db.models.station_template import StationTemplate


async def test_get_map_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/map")

    assert response.status_code == 401


async def test_get_map_returns_stations_and_refineries(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add(
        StationTemplate(
            osm_id="map-1",
            name="Map Station",
            latitude=56.6,
            longitude=47.9,
            base_price="3500000.00",
            metadata_json={"settlement": "Йошкар-Ола"},
        )
    )
    db_session.add(Refinery(name="Map Refinery", latitude=56.7, longitude=47.95))
    await db_session.commit()

    response = await client.post(
        "/api/auth/register",
        json={
            "email": "mapviewer@example.com",
            "password": "correcthorsebattery",
            "display_name": "MapViewer",
        },
    )
    assert response.status_code == 201

    map_response = await client.get("/api/map")

    assert map_response.status_code == 200
    body = map_response.json()
    assert any(s["name"] == "Map Station" for s in body["stations"])
    assert any(r["name"] == "Map Refinery" for r in body["refineries"])
