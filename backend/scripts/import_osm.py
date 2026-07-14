"""Import gas stations from a prepared GeoJSON file into StationTemplate.

This script reads a local GeoJSON file only — it never calls any external
mapping API. Prepare the GeoJSON file in advance (e.g. from an OSM export).
Also runs automatically on every app startup via app.core.release.

Usage:
    python -m scripts.import_osm [path/to/stations.geojson]
"""

import asyncio
import sys
from pathlib import Path

from app.db.session import async_session_factory
from app.services.map_import_service import parse_station_features, upsert_station_templates

DEFAULT_GEOJSON_PATH = Path(__file__).resolve().parent.parent / "data" / "mari_el_stations.geojson"


async def main(geojson_path: Path) -> None:
    features = parse_station_features(geojson_path)

    async with async_session_factory() as db:
        processed = await upsert_station_templates(db, features)

    print(f"Imported {processed} station template(s) from {geojson_path}")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_GEOJSON_PATH
    asyncio.run(main(path))
