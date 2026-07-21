import json
import random
import resource
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode
from app.db.models.station_template import StationTemplate
from app.db.models.traffic_light import TrafficLight
from app.db.models.truck import Truck
from app.db.models.vehicle import Vehicle
from app.services.routing_service import haversine_km

# An intersection (not a pass-through point) is a node touching at least this
# many distinct neighbors; only these get a traffic light (Этап 14.2).
MIN_INTERSECTION_DEGREE = 3
DEFAULT_LIGHT_RED_SECONDS = 20.0
DEFAULT_LIGHT_YELLOW_SECONDS = 3.0
DEFAULT_LIGHT_GREEN_SECONDS = 25.0

# Синтетическая сеть троллейбусных линий (Этап 14.4): нет реальных данных о
# линиях, поэтому помечаем trolleybus_wire=true на дорогах этих типов —
# трамвайно-троллейбусные линии в реальности идут вдоль главных улиц.
TROLLEYBUS_WIRE_ROAD_TYPES = frozenset({"trunk", "primary"})


@dataclass(frozen=True)
class StationFeature:
    osm_id: str | None
    name: str
    latitude: float
    longitude: float
    base_price: Decimal
    metadata_json: dict[str, object]


class InvalidGeoJsonError(Exception):
    pass


def parse_station_features(geojson_path: Path) -> list[StationFeature]:
    raw = json.loads(geojson_path.read_text(encoding="utf-8"))

    if raw.get("type") != "FeatureCollection":
        raise InvalidGeoJsonError("Expected a GeoJSON FeatureCollection")

    features: list[StationFeature] = []
    for raw_feature in raw["features"]:
        properties = raw_feature["properties"]
        longitude, latitude = raw_feature["geometry"]["coordinates"]
        features.append(
            StationFeature(
                osm_id=properties.get("osm_id"),
                name=properties["name"],
                latitude=latitude,
                longitude=longitude,
                base_price=Decimal(str(properties["base_price"])),
                metadata_json={"settlement": properties.get("settlement")},
            )
        )

    return features


async def upsert_station_templates(db: AsyncSession, features: list[StationFeature]) -> int:
    osm_ids = [feature.osm_id for feature in features if feature.osm_id is not None]

    existing_by_osm_id: dict[str, StationTemplate] = {}
    if osm_ids:
        result = await db.execute(
            select(StationTemplate).where(StationTemplate.osm_id.in_(osm_ids))
        )
        existing_by_osm_id = {
            station.osm_id: station for station in result.scalars() if station.osm_id is not None
        }

    processed = 0
    for feature in features:
        existing = existing_by_osm_id.get(feature.osm_id) if feature.osm_id else None
        if existing is not None:
            existing.name = feature.name
            existing.latitude = feature.latitude
            existing.longitude = feature.longitude
            existing.base_price = feature.base_price
            existing.metadata_json = feature.metadata_json
        else:
            db.add(
                StationTemplate(
                    osm_id=feature.osm_id,
                    name=feature.name,
                    latitude=feature.latitude,
                    longitude=feature.longitude,
                    base_price=feature.base_price,
                    metadata_json=feature.metadata_json,
                )
            )
        processed += 1

    await db.commit()
    return processed


@dataclass(frozen=True)
class RoadSegmentFeature:
    coordinates: list[tuple[float, float]]
    road_type: str
    max_speed_kmh: float
    is_one_way: bool


def parse_road_features(geojson_path: Path) -> list[RoadSegmentFeature]:
    raw = json.loads(geojson_path.read_text(encoding="utf-8"))

    if raw.get("type") != "FeatureCollection":
        raise InvalidGeoJsonError("Expected a GeoJSON FeatureCollection")

    features: list[RoadSegmentFeature] = []
    for raw_feature in raw["features"]:
        properties = raw_feature["properties"]
        geometry = raw_feature["geometry"]
        if geometry.get("type") != "LineString":
            raise InvalidGeoJsonError("Expected LineString geometry for road segments")

        coordinates = [(float(lon), float(lat)) for lon, lat in geometry["coordinates"]]
        features.append(
            RoadSegmentFeature(
                coordinates=coordinates,
                road_type=properties.get("road_type", "local"),
                max_speed_kmh=float(properties.get("max_speed_kmh", 50.0)),
                is_one_way=bool(properties.get("oneway", False)),
            )
        )

    return features


def _coordinate_key(longitude: float, latitude: float) -> tuple[float, float]:
    return (round(longitude, 6), round(latitude, 6))


_INSERT_BATCH_SIZE = 5000


async def _bulk_insert_in_batches(
    db: AsyncSession,
    table: type[RoadNode] | type[RoadEdge] | type[TrafficLight],
    rows: list[dict[str, object]],
) -> None:
    # A single INSERT with all rows keeps every row dict (and SQLAlchemy's own
    # executemany parameter buffer) alive in memory at once; for a real OSM
    # export (tens of thousands of rows) that peak is the difference between
    # fitting in a small deploy container and getting OOM-killed. Batching
    # bounds peak memory regardless of how large the road file grows.
    total_batches = (len(rows) + _INSERT_BATCH_SIZE - 1) // _INSERT_BATCH_SIZE
    for batch_index, start in enumerate(range(0, len(rows), _INSERT_BATCH_SIZE), start=1):
        await db.execute(insert(table), rows[start : start + _INSERT_BATCH_SIZE])
        rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        print(
            f"[build_road_graph] {table.__tablename__} batch {batch_index}/{total_batches}, "
            f"rss={rss_mb:.0f}MB",
            flush=True,
        )


async def build_road_graph(
    db: AsyncSession, features: list[RoadSegmentFeature], *, rng: random.Random | None = None
) -> tuple[int, int]:
    """Build (or rebuild) the road graph from parsed LineString segments.

    Nodes are deduplicated by coordinate and reused across runs. Edges are
    fully rebuilt on every run since nothing references them by foreign key.
    Traffic lights (Этап 14.2) are also fully rebuilt: seeded at every node
    that touches >= MIN_INTERSECTION_DEGREE distinct neighbors (a real
    intersection, not a pass-through point on a curving road).

    Uses bulk Core INSERT statements (not one ORM object + db.add() per row):
    a real OSM export can be tens of thousands of nodes/edges, and building
    that many ORM-tracked instances in the session's identity map is slow
    enough (and memory-heavy enough) to blow past deploy healthcheck windows
    on every single boot. Primary keys are client-side uuid4 (see the models),
    so rows can be inserted without needing RETURNING to learn their id.
    """
    rng = rng or random.Random()
    t0 = time.monotonic()

    def _log(label: str) -> None:
        # Временная диагностика зависаний деплоя на Railway (см. коммит).
        print(f"[build_road_graph] {label}: +{time.monotonic() - t0:.1f}s", flush=True)

    existing_nodes = (
        await db.execute(select(RoadNode.id, RoadNode.longitude, RoadNode.latitude))
    ).all()
    _log(f"selected {len(existing_nodes)} existing nodes")
    node_id_by_coordinate: dict[tuple[float, float], uuid.UUID] = {
        _coordinate_key(longitude, latitude): node_id
        for node_id, longitude, latitude in existing_nodes
    }

    new_node_rows: list[dict[str, object]] = []
    for feature in features:
        for longitude, latitude in feature.coordinates:
            key = _coordinate_key(longitude, latitude)
            if key not in node_id_by_coordinate:
                node_id = uuid.uuid4()
                node_id_by_coordinate[key] = node_id
                new_node_rows.append({"id": node_id, "latitude": latitude, "longitude": longitude})
    _log(f"computed {len(new_node_rows)} new node rows")

    if new_node_rows:
        await _bulk_insert_in_batches(db, RoadNode, new_node_rows)
    _log("inserted new nodes")

    # Rebuilding replaces every edge with a fresh id, so any vehicle/truck
    # mid-route on the old graph would otherwise block this DELETE with a
    # foreign key violation (and, if it didn't, would be left silently
    # pointing at an id that no longer exists). Clearing them here is the
    # honest outcome of "the road network just changed under you" — the
    # game's own spawn logic replaces them within moments; there is no
    # reroute-from-scratch mechanism for a fully vanished edge, only for a
    # closed one (see _reroute_truck), so leaving current_edge_id dangling
    # would strand them forever instead.
    await db.execute(delete(Vehicle).where(Vehicle.current_edge_id.is_not(None)))
    await db.execute(delete(Truck).where(Truck.current_edge_id.is_not(None)))
    _log("cleared vehicles/trucks referencing old edges")

    await db.execute(delete(RoadEdge))
    _log("deleted old edges")

    neighbor_keys: dict[tuple[float, float], set[tuple[float, float]]] = {}
    edge_rows: list[dict[str, object]] = []
    for feature in features:
        for (lon_a, lat_a), (lon_b, lat_b) in pairwise(feature.coordinates):
            key_a = _coordinate_key(lon_a, lat_a)
            key_b = _coordinate_key(lon_b, lat_b)
            neighbor_keys.setdefault(key_a, set()).add(key_b)
            neighbor_keys.setdefault(key_b, set()).add(key_a)

            node_a_id = node_id_by_coordinate[key_a]
            node_b_id = node_id_by_coordinate[key_b]
            distance_km = haversine_km(lat_a, lon_a, lat_b, lon_b)
            trolleybus_wire = feature.road_type in TROLLEYBUS_WIRE_ROAD_TYPES

            edge_rows.append(
                {
                    "id": uuid.uuid4(),
                    "from_node_id": node_a_id,
                    "to_node_id": node_b_id,
                    "distance_km": distance_km,
                    "max_speed_kmh": feature.max_speed_kmh,
                    "road_type": feature.road_type,
                    "is_one_way": feature.is_one_way,
                    "trolleybus_wire": trolleybus_wire,
                }
            )
            if not feature.is_one_way:
                edge_rows.append(
                    {
                        "id": uuid.uuid4(),
                        "from_node_id": node_b_id,
                        "to_node_id": node_a_id,
                        "distance_km": distance_km,
                        "max_speed_kmh": feature.max_speed_kmh,
                        "road_type": feature.road_type,
                        "is_one_way": feature.is_one_way,
                        "trolleybus_wire": trolleybus_wire,
                    }
                )

    _log(f"computed {len(edge_rows)} edge rows")

    if edge_rows:
        await _bulk_insert_in_batches(db, RoadEdge, edge_rows)
    _log("inserted edges")

    await db.execute(delete(TrafficLight))
    cycle_length = (
        DEFAULT_LIGHT_RED_SECONDS + DEFAULT_LIGHT_YELLOW_SECONDS + DEFAULT_LIGHT_GREEN_SECONDS
    )
    light_rows: list[dict[str, object]] = [
        {
            "id": uuid.uuid4(),
            "road_node_id": node_id_by_coordinate[key],
            "red_seconds": DEFAULT_LIGHT_RED_SECONDS,
            "yellow_seconds": DEFAULT_LIGHT_YELLOW_SECONDS,
            "green_seconds": DEFAULT_LIGHT_GREEN_SECONDS,
            "offset_seconds": rng.uniform(0.0, cycle_length),
        }
        for key, neighbors in neighbor_keys.items()
        if len(neighbors) >= MIN_INTERSECTION_DEGREE
    ]
    if light_rows:
        await _bulk_insert_in_batches(db, TrafficLight, light_rows)
    _log(f"inserted {len(light_rows)} traffic lights")

    await db.commit()
    _log("committed")
    return len(node_id_by_coordinate), len(edge_rows)
