"""Run pending migrations and seed static map data. Idempotent; safe on every boot.

Runs inside the same process and interpreter as the running app (called
from the FastAPI lifespan in app.main), so it never depends on how a
deployment platform resolves a separate `python`/`alembic` executable for
a pre-deploy command.
"""

import asyncio
import resource
import time
from pathlib import Path

from alembic import command
from alembic.config import Config

from scripts import build_road_graph, import_osm, seed_game_data

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _checkpoint(label: str, start: float) -> None:
    # Временная диагностика зависаний деплоя на Railway (см. коммит):
    # ru_maxrss — пиковая RSS-память процесса в КБ на Linux.
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    elapsed = time.monotonic() - start
    print(f"[release] {label}: +{elapsed:.1f}s, rss={rss_mb:.0f}MB", flush=True)


async def run_release_tasks() -> None:
    start = time.monotonic()
    _checkpoint("start", start)

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    # alembic's async env.py drives its own asyncio.run(); run it on a
    # separate thread so it doesn't collide with the loop we're called from.
    await asyncio.to_thread(command.upgrade, config, "head")
    _checkpoint("migrations done", start)

    await import_osm.main(import_osm.DEFAULT_GEOJSON_PATH)
    _checkpoint("stations imported", start)

    await seed_game_data.main()
    _checkpoint("refinery seeded", start)

    await build_road_graph.main(build_road_graph.DEFAULT_GEOJSON_PATH)
    _checkpoint("road graph done", start)
