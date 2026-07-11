import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.station_template import StationTemplate
from app.services.map_import_service import parse_station_features, upsert_station_templates


def _write_geojson(path: Path, features: list[dict]) -> None:
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8"
    )


def _feature(osm_id: str, name: str, lon: float, lat: float, price: int) -> dict:
    return {
        "type": "Feature",
        "properties": {"osm_id": osm_id, "name": name, "base_price": price, "settlement": "Test"},
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


async def test_parse_station_features_reads_geojson(tmp_path: Path) -> None:
    geojson_path = tmp_path / "stations.geojson"
    _write_geojson(geojson_path, [_feature("a1", "Station A", 47.88, 56.63, 3500000)])

    features = parse_station_features(geojson_path)

    assert len(features) == 1
    assert features[0].osm_id == "a1"
    assert features[0].name == "Station A"
    assert features[0].longitude == 47.88
    assert features[0].latitude == 56.63
    assert str(features[0].base_price) == "3500000"


async def test_upsert_station_templates_inserts_new_rows(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    geojson_path = tmp_path / "stations.geojson"
    _write_geojson(
        geojson_path,
        [
            _feature("b1", "Station B1", 47.0, 56.0, 3000000),
            _feature("b2", "Station B2", 47.1, 56.1, 3100000),
        ],
    )
    features = parse_station_features(geojson_path)

    processed = await upsert_station_templates(db_session, features)

    assert processed == 2
    result = await db_session.execute(
        select(StationTemplate).where(StationTemplate.osm_id.in_(["b1", "b2"]))
    )
    stations = {s.osm_id: s for s in result.scalars()}
    assert stations["b1"].name == "Station B1"
    assert stations["b2"].name == "Station B2"


async def test_upsert_station_templates_is_idempotent(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    geojson_path = tmp_path / "stations.geojson"
    _write_geojson(geojson_path, [_feature("c1", "Station C", 47.0, 56.0, 3000000)])
    features = parse_station_features(geojson_path)

    await upsert_station_templates(db_session, features)
    await upsert_station_templates(db_session, features)

    result = await db_session.execute(select(StationTemplate).where(StationTemplate.osm_id == "c1"))
    stations = result.scalars().all()
    assert len(stations) == 1


async def test_upsert_station_templates_updates_existing_row_on_rerun(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    geojson_path = tmp_path / "stations.geojson"
    _write_geojson(geojson_path, [_feature("d1", "Station D old", 47.0, 56.0, 3000000)])
    await upsert_station_templates(db_session, parse_station_features(geojson_path))

    _write_geojson(geojson_path, [_feature("d1", "Station D new", 47.5, 56.5, 3400000)])
    await upsert_station_templates(db_session, parse_station_features(geojson_path))

    result = await db_session.execute(select(StationTemplate).where(StationTemplate.osm_id == "d1"))
    station = result.scalar_one()
    assert station.name == "Station D new"
    assert str(station.base_price) == "3400000.00"
