"""Release-phase command for deployment: run migrations, then seed static map data.

Meant to run once per deploy (e.g. as a Railway pre-deploy command). Every
step it calls is idempotent, so re-running it on top of already-seeded data
is safe.

Usage:
    python -m scripts.release
"""

import subprocess
import sys
from pathlib import Path

from alembic.config import Config

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def _upgrade_database() -> None:
    # Alembic ships no __main__.py, so it can't be run via `python -m alembic`;
    # invoke it through its public Python API instead of a subprocess.
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(config, "head")


def main() -> None:
    _upgrade_database()
    _run(sys.executable, "-m", "scripts.import_osm")
    _run(sys.executable, "-m", "scripts.seed_game_data")
    _run(sys.executable, "-m", "scripts.build_road_graph")


if __name__ == "__main__":
    main()
