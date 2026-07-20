import json
import random
from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode
from app.db.models.station_template import StationTemplate
from app.db.models.traffic_light import TrafficLight
from app.services.routing_service import haversine_km

# An intersection (not a pass-through point) is a node touching at least this
# many distinct neighbors; only these get a traffic light (Этап 14.2).
MIN_INTERSECTION_DEGREE = 3
DEFAULT_LIGHT_RED_SECONDS = 20.0
DEFAULT_LIGHT_YELLOW_SECONDS = 3.0
DEFAULT_LIGHT_GREEN_SECONDS = 25.0


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


async def build_road_graph(
    db: AsyncSession, features: list[RoadSegmentFeature], *, rng: random.Random | None = None
) -> tuple[int, int]:
    """Build (or rebuild) the road graph from parsed LineString segments.

    Nodes are deduplicated by coordinate and reused across runs. Edges are
    fully rebuilt on every run since nothing references them by foreign key.
    Traffic lights (Этап 14.2) are also fully rebuilt: seeded at every node
    that touches >= MIN_INTERSECTION_DEGREE distinct neighbors (a real
    intersection, not a pass-through point on a curving road).
    """
    rng = rng or random.Random()

    existing_nodes = (await db.execute(select(RoadNode))).scalars().all()
    node_by_coordinate: dict[tuple[float, float], RoadNode] = {
        _coordinate_key(node.longitude, node.latitude): node for node in existing_nodes
    }

    for feature in features:
        for longitude, latitude in feature.coordinates:
            key = _coordinate_key(longitude, latitude)
            if key not in node_by_coordinate:
                node = RoadNode(latitude=latitude, longitude=longitude)
                db.add(node)
                node_by_coordinate[key] = node

    await db.flush()

    await db.execute(delete(RoadEdge))

    neighbor_keys: dict[tuple[float, float], set[tuple[float, float]]] = {}
    edge_count = 0
    for feature in features:
        for (lon_a, lat_a), (lon_b, lat_b) in pairwise(feature.coordinates):
            key_a = _coordinate_key(lon_a, lat_a)
            key_b = _coordinate_key(lon_b, lat_b)
            neighbor_keys.setdefault(key_a, set()).add(key_b)
            neighbor_keys.setdefault(key_b, set()).add(key_a)

            node_a = node_by_coordinate[key_a]
            node_b = node_by_coordinate[key_b]
            distance_km = haversine_km(lat_a, lon_a, lat_b, lon_b)

            db.add(
                RoadEdge(
                    from_node_id=node_a.id,
                    to_node_id=node_b.id,
                    distance_km=distance_km,
                    max_speed_kmh=feature.max_speed_kmh,
                    road_type=feature.road_type,
                    is_one_way=feature.is_one_way,
                )
            )
            edge_count += 1
            if not feature.is_one_way:
                db.add(
                    RoadEdge(
                        from_node_id=node_b.id,
                        to_node_id=node_a.id,
                        distance_km=distance_km,
                        max_speed_kmh=feature.max_speed_kmh,
                        road_type=feature.road_type,
                        is_one_way=feature.is_one_way,
                    )
                )
                edge_count += 1

    await db.execute(delete(TrafficLight))
    cycle_length = (
        DEFAULT_LIGHT_RED_SECONDS + DEFAULT_LIGHT_YELLOW_SECONDS + DEFAULT_LIGHT_GREEN_SECONDS
    )
    for key, neighbors in neighbor_keys.items():
        if len(neighbors) < MIN_INTERSECTION_DEGREE:
            continue
        db.add(
            TrafficLight(
                road_node_id=node_by_coordinate[key].id,
                red_seconds=DEFAULT_LIGHT_RED_SECONDS,
                yellow_seconds=DEFAULT_LIGHT_YELLOW_SECONDS,
                green_seconds=DEFAULT_LIGHT_GREEN_SECONDS,
                offset_seconds=rng.uniform(0.0, cycle_length),
            )
        )

    await db.commit()
    return len(node_by_coordinate), edge_count
