"""Run pending migrations and seed static map data. Idempotent; safe on every boot.

Runs inside the same process and interpreter as the running app (called
from the FastAPI lifespan in app.main), so it never depends on how a
deployment platform resolves a separate `python`/`alembic` executable for
a pre-deploy command.
"""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

from scripts import build_road_graph, import_osm, seed_game_data

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


async def run_release_tasks() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    # alembic's async env.py drives its own asyncio.run(); run it on a
    # separate thread so it doesn't collide with the loop we're called from.
    await asyncio.to_thread(command.upgrade, config, "head")

    await import_osm.main(import_osm.DEFAULT_GEOJSON_PATH)
    await seed_game_data.main()
    await build_road_graph.main(build_road_graph.DEFAULT_GEOJSON_PATH)
