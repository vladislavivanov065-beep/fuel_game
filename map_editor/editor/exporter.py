"""Convert an editor Project into the exact GeoJSON formats fuel_game expects.

Road format -> parse_road_features() in
    fuel_game/backend/app/services/map_import_service.py
Station format -> parse_station_features() in the same module.
Refinery has no GeoJSON of its own: it is three constants in
    fuel_game/backend/scripts/seed_game_data.py.

Key subtlety this module handles: the backend dedups road nodes by rounding
coordinates to 6 decimal places (~0.11 m). Two lines drawn by hand rarely
land on the *exact* same coordinate even when the user intends an
intersection. So before exporting we cluster all road vertices that are
within SNAP_TOLERANCE_M of each other and collapse each cluster to a single
shared coordinate -- mirroring what a careful GeoJSON editor would do by
hand, but automatically.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .models import MIN_INTERSECTION_DEGREE, Project, TrafficLightMarker

SNAP_TOLERANCE_M = 5.0
LIGHT_SNAP_TOLERANCE_M = 15.0
EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


@dataclass(frozen=True)
class MergeResult:
    # Merged, rounded (lon, lat) coordinates per road, same order/length as input
    # minus any consecutive duplicates collapsed by merging.
    merged_roads: list[list[tuple[float, float]]]
    # Adjacency exactly as fuel_game's build_road_graph computes it: for every
    # pair of consecutive points on any road, both directions are neighbors,
    # irrespective of `oneway` (oneway only affects which RoadEdge rows get
    # created, not traffic-light placement).
    neighbors: dict[tuple[float, float], set[tuple[float, float]]]


def _round_coord(lon: float, lat: float) -> tuple[float, float]:
    return (round(lon, 6), round(lat, 6))


def merge_road_vertices(project: Project, tolerance_m: float = SNAP_TOLERANCE_M) -> MergeResult:
    points: list[tuple[float, float]] = []
    index_by_road: list[list[int]] = []
    for road in project.roads:
        indices = []
        for lon, lat in road.coordinates:
            indices.append(len(points))
            points.append((lon, lat))
        index_by_road.append(indices)

    uf = _UnionFind(len(points))
    for i in range(len(points)):
        lon_i, lat_i = points[i]
        for j in range(i + 1, len(points)):
            lon_j, lat_j = points[j]
            # Cheap pre-filter before the trig-heavy haversine call.
            if abs(lat_i - lat_j) > 0.01 or abs(lon_i - lon_j) > 0.02:
                continue
            if haversine_m(lat_i, lon_i, lat_j, lon_j) <= tolerance_m:
                uf.union(i, j)

    cluster_points: dict[int, list[tuple[float, float]]] = {}
    for i, (lon, lat) in enumerate(points):
        cluster_points.setdefault(uf.find(i), []).append((lon, lat))

    cluster_coord: dict[int, tuple[float, float]] = {}
    for root, members in cluster_points.items():
        avg_lon = sum(p[0] for p in members) / len(members)
        avg_lat = sum(p[1] for p in members) / len(members)
        cluster_coord[root] = _round_coord(avg_lon, avg_lat)

    merged_roads: list[list[tuple[float, float]]] = []
    for indices in index_by_road:
        coords = [cluster_coord[uf.find(i)] for i in indices]
        deduped: list[tuple[float, float]] = []
        for coord in coords:
            if not deduped or deduped[-1] != coord:
                deduped.append(coord)
        merged_roads.append(deduped)

    neighbors: dict[tuple[float, float], set[tuple[float, float]]] = {}
    for coords in merged_roads:
        for a, b in zip(coords, coords[1:]):
            neighbors.setdefault(a, set()).add(b)
            neighbors.setdefault(b, set()).add(a)

    return MergeResult(merged_roads=merged_roads, neighbors=neighbors)


def to_roads_geojson(project: Project, tolerance_m: float = SNAP_TOLERANCE_M) -> dict[str, Any]:
    merge = merge_road_vertices(project, tolerance_m)
    features = []
    for road, coords in zip(project.roads, merge.merged_roads):
        if len(coords) < 2:
            continue  # collapsed entirely into one point after snapping
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "road_type": road.road_type,
                    "max_speed_kmh": road.max_speed_kmh,
                    "oneway": road.oneway,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[lon, lat] for lon, lat in coords],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def to_stations_geojson(project: Project) -> dict[str, Any]:
    features = []
    for station in project.stations:
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "osm_id": station.osm_id,
                    "name": station.name,
                    # UI works in rubles; fuel_game stores kopecks (base_price = rub * 100).
                    "base_price": round(station.base_price_rub * 100),
                    "settlement": station.settlement,
                },
                "geometry": {"type": "Point", "coordinates": [station.lon, station.lat]},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def refinery_export(project: Project) -> dict[str, Any] | None:
    if project.refinery is None:
        return None
    r = project.refinery
    snippet = (
        f'REFINERY_NAME = "{r.name}"\n'
        f"REFINERY_LATITUDE = {r.lat}\n"
        f"REFINERY_LONGITUDE = {r.lon}\n"
    )
    return {"name": r.name, "lat": r.lat, "lon": r.lon, "seed_game_data_snippet": snippet}


@dataclass(frozen=True)
class LightCheck:
    id: str
    lon: float
    lat: float
    snapped_to: tuple[float, float] | None
    distance_m: float | None
    degree: int
    ok: bool
    message: str


def validate_traffic_lights(
    project: Project,
    tolerance_m: float = SNAP_TOLERANCE_M,
    snap_tolerance_m: float = LIGHT_SNAP_TOLERANCE_M,
) -> list[LightCheck]:
    merge = merge_road_vertices(project, tolerance_m)
    node_coords = list(merge.neighbors.keys())
    checks: list[LightCheck] = []

    def check_one(marker: TrafficLightMarker) -> LightCheck:
        nearest: tuple[float, float] | None = None
        nearest_dist = math.inf
        for lon, lat in node_coords:
            dist = haversine_m(marker.lat, marker.lon, lat, lon)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest = (lon, lat)

        if nearest is None or nearest_dist > snap_tolerance_m:
            return LightCheck(
                id=marker.id,
                lon=marker.lon,
                lat=marker.lat,
                snapped_to=None,
                distance_m=None,
                degree=0,
                ok=False,
                message=(
                    "Нет дорожного узла поблизости "
                    f"(ближе {snap_tolerance_m:.0f} м) — светофор не появится."
                ),
            )

        degree = len(merge.neighbors.get(nearest, ()))
        ok = degree >= MIN_INTERSECTION_DEGREE
        message = (
            f"OK: {degree} примыкающих сегмента(ов) — светофор будет создан."
            if ok
            else (
                f"Только {degree} примыкающих сегмента(ов), нужно >= "
                f"{MIN_INTERSECTION_DEGREE}. Добавьте ещё один дорожный сегмент "
                "в эту точку."
            )
        )
        return LightCheck(
            id=marker.id,
            lon=marker.lon,
            lat=marker.lat,
            snapped_to=nearest,
            distance_m=nearest_dist,
            degree=degree,
            ok=ok,
            message=message,
        )

    for marker in project.traffic_lights:
        checks.append(check_one(marker))
    return checks
