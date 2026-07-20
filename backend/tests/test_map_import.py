import json
import random
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode
from app.db.models.station_template import StationTemplate
from app.db.models.traffic_light import TrafficLight
from app.services.map_import_service import (
    build_road_graph,
    parse_road_features,
    parse_station_features,
    upsert_station_templates,
)


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


def _road_feature(
    coordinates: list[list[float]],
    road_type: str = "local",
    max_speed_kmh: float = 50.0,
    oneway: bool = False,
) -> dict:
    return {
        "type": "Feature",
        "properties": {"road_type": road_type, "max_speed_kmh": max_speed_kmh, "oneway": oneway},
        "geometry": {"type": "LineString", "coordinates": coordinates},
    }


def _write_road_geojson(path: Path, features: list[dict]) -> None:
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8"
    )


async def test_parse_road_features_reads_linestrings(tmp_path: Path) -> None:
    geojson_path = tmp_path / "roads.geojson"
    _write_road_geojson(
        geojson_path,
        [_road_feature([[47.0, 56.0], [47.1, 56.1]], road_type="trunk", max_speed_kmh=90.0)],
    )

    features = parse_road_features(geojson_path)

    assert len(features) == 1
    assert features[0].coordinates == [(47.0, 56.0), (47.1, 56.1)]
    assert features[0].road_type == "trunk"
    assert features[0].max_speed_kmh == 90.0
    assert features[0].is_one_way is False


async def test_build_road_graph_dedupes_shared_nodes(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    geojson_path = tmp_path / "roads.geojson"
    _write_road_geojson(
        geojson_path,
        [
            _road_feature([[47.0, 56.0], [47.1, 56.1]]),
            _road_feature([[47.1, 56.1], [47.2, 56.2]]),
        ],
    )
    features = parse_road_features(geojson_path)

    node_count, edge_count = await build_road_graph(db_session, features)

    assert node_count == 3
    assert edge_count == 4

    nodes = (await db_session.execute(select(RoadNode))).scalars().all()
    assert len(nodes) == 3


async def test_build_road_graph_is_idempotent_for_nodes(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    geojson_path = tmp_path / "roads.geojson"
    _write_road_geojson(geojson_path, [_road_feature([[47.0, 56.0], [47.1, 56.1]])])
    features = parse_road_features(geojson_path)

    await build_road_graph(db_session, features)
    node_count, edge_count = await build_road_graph(db_session, features)

    assert node_count == 2
    assert edge_count == 2

    nodes = (await db_session.execute(select(RoadNode))).scalars().all()
    edges = (await db_session.execute(select(RoadEdge))).scalars().all()
    assert len(nodes) == 2
    assert len(edges) == 2


async def test_build_road_graph_one_way_creates_single_edge(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    geojson_path = tmp_path / "roads.geojson"
    _write_road_geojson(geojson_path, [_road_feature([[47.0, 56.0], [47.1, 56.1]], oneway=True)])
    features = parse_road_features(geojson_path)

    node_count, edge_count = await build_road_graph(db_session, features)

    assert node_count == 2
    assert edge_count == 1


def _write_three_way_intersection(tmp_path: Path) -> Path:
    path = tmp_path / "roads.geojson"
    _write_road_geojson(
        path,
        [
            _road_feature([[47.0, 56.0], [47.1, 56.1]]),
            _road_feature([[47.1, 56.1], [47.2, 56.0]]),
            _road_feature([[47.1, 56.1], [47.2, 56.2]]),
        ],
    )
    return path


async def test_build_road_graph_seeds_traffic_lights_only_at_intersections(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    features = parse_road_features(_write_three_way_intersection(tmp_path))
    await build_road_graph(db_session, features, rng=random.Random(1))

    nodes = (await db_session.execute(select(RoadNode))).scalars().all()
    lights = (await db_session.execute(select(TrafficLight))).scalars().all()

    assert len(nodes) == 4
    assert len(lights) == 1

    intersection_node = next(
        node for node in nodes if node.latitude == 56.1 and node.longitude == 47.1
    )
    assert lights[0].road_node_id == intersection_node.id
    assert lights[0].red_seconds > 0
    assert lights[0].green_seconds > 0


async def test_build_road_graph_traffic_lights_are_rebuilt_idempotently(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    features = parse_road_features(_write_three_way_intersection(tmp_path))
    await build_road_graph(db_session, features, rng=random.Random(1))
    await build_road_graph(db_session, features, rng=random.Random(2))

    lights = (await db_session.execute(select(TrafficLight))).scalars().all()
    assert len(lights) == 1
