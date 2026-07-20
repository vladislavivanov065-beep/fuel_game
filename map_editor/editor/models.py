"""In-memory project schema for the map editor.

Mirrors, in spirit, the two GeoJSON formats consumed by fuel_game's
``backend/app/services/map_import_service.py`` (parse_road_features /
parse_station_features), plus the standalone refinery constants from
``backend/scripts/seed_game_data.py``. Traffic lights have no source file of
their own in fuel_game -- they are derived automatically from road topology
(any node touching >= 3 distinct neighbors gets one). Here they are stored
only as placement hints so the editor can warn when a hint will not actually
produce a light after import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALID_ROAD_TYPES = {"local", "trunk", "primary"}

# Same threshold as MIN_INTERSECTION_DEGREE in map_import_service.py.
MIN_INTERSECTION_DEGREE = 3


class ProjectValidationError(ValueError):
    pass


@dataclass
class RoadFeature:
    id: str
    road_type: str
    max_speed_kmh: float
    oneway: bool
    coordinates: list[tuple[float, float]]  # [(lon, lat), ...], >= 2 points

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "road_type": self.road_type,
            "max_speed_kmh": self.max_speed_kmh,
            "oneway": self.oneway,
            "coordinates": [[lon, lat] for lon, lat in self.coordinates],
        }

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> RoadFeature:
        coords = raw.get("coordinates") or []
        if len(coords) < 2:
            raise ProjectValidationError(f"Road {raw.get('id')!r} needs at least 2 points")
        road_type = raw.get("road_type", "local")
        if road_type not in VALID_ROAD_TYPES:
            raise ProjectValidationError(
                f"Road {raw.get('id')!r} has unknown road_type {road_type!r}"
            )
        return RoadFeature(
            id=str(raw["id"]),
            road_type=road_type,
            max_speed_kmh=float(raw.get("max_speed_kmh", 50.0)),
            oneway=bool(raw.get("oneway", False)),
            coordinates=[(float(lon), float(lat)) for lon, lat in coords],
        )


@dataclass
class StationFeature:
    id: str
    osm_id: str
    name: str
    base_price_rub: float
    settlement: str
    lon: float
    lat: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "osm_id": self.osm_id,
            "name": self.name,
            "base_price_rub": self.base_price_rub,
            "settlement": self.settlement,
            "lon": self.lon,
            "lat": self.lat,
        }

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> StationFeature:
        if not raw.get("name"):
            raise ProjectValidationError(f"Station {raw.get('id')!r} needs a name")
        if not raw.get("osm_id"):
            raise ProjectValidationError(f"Station {raw.get('id')!r} needs an osm_id")
        return StationFeature(
            id=str(raw["id"]),
            osm_id=str(raw["osm_id"]),
            name=str(raw["name"]),
            base_price_rub=float(raw.get("base_price_rub", 0)),
            settlement=str(raw.get("settlement", "")),
            lon=float(raw["lon"]),
            lat=float(raw["lat"]),
        )


@dataclass
class Refinery:
    name: str
    lon: float
    lat: float

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "lon": self.lon, "lat": self.lat}

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> Refinery:
        return Refinery(name=str(raw.get("name", "")), lon=float(raw["lon"]), lat=float(raw["lat"]))


@dataclass
class TrafficLightMarker:
    id: str
    lon: float
    lat: float

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "lon": self.lon, "lat": self.lat}

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> TrafficLightMarker:
        return TrafficLightMarker(id=str(raw["id"]), lon=float(raw["lon"]), lat=float(raw["lat"]))


@dataclass
class Project:
    roads: list[RoadFeature] = field(default_factory=list)
    stations: list[StationFeature] = field(default_factory=list)
    refinery: Refinery | None = None
    traffic_lights: list[TrafficLightMarker] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "roads": [r.to_dict() for r in self.roads],
            "stations": [s.to_dict() for s in self.stations],
            "refinery": self.refinery.to_dict() if self.refinery else None,
            "traffic_lights": [t.to_dict() for t in self.traffic_lights],
        }

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> Project:
        return Project(
            roads=[RoadFeature.from_dict(r) for r in raw.get("roads", [])],
            stations=[StationFeature.from_dict(s) for s in raw.get("stations", [])],
            refinery=Refinery.from_dict(raw["refinery"]) if raw.get("refinery") else None,
            traffic_lights=[
                TrafficLightMarker.from_dict(t) for t in raw.get("traffic_lights", [])
            ],
        )
