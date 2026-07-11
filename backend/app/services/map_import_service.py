import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.station_template import StationTemplate


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
