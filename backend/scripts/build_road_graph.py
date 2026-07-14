"""Build the road graph from a prepared GeoJSON file of road segments.

This script reads a local GeoJSON file only — it never calls any external
mapping API. Prepare the GeoJSON file in advance (e.g. from an OSM export).
Also runs automatically on every app startup via app.core.release.

Usage:
    python -m scripts.build_road_graph [path/to/roads.geojson]
"""

import asyncio
import sys
from pathlib import Path

from app.db.session import async_session_factory
from app.services.map_import_service import build_road_graph, parse_road_features

DEFAULT_GEOJSON_PATH = Path(__file__).resolve().parent.parent / "data" / "mari_el_roads.geojson"


async def main(geojson_path: Path) -> None:
    features = parse_road_features(geojson_path)

    async with async_session_factory() as db:
        node_count, edge_count = await build_road_graph(db, features)

    print(f"Road graph ready: {node_count} node(s), {edge_count} edge(s) from {geojson_path}")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_GEOJSON_PATH
    asyncio.run(main(path))
