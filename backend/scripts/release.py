"""Release-phase command for deployment: run migrations, then seed static map data.

Meant to run once per deploy (e.g. as a Railway pre-deploy command). Every
step it calls is idempotent, so re-running it on top of already-seeded data
is safe.

Usage:
    python -m scripts.release
"""

import subprocess
import sys


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def main() -> None:
    _run("alembic", "upgrade", "head")
    _run(sys.executable, "-m", "scripts.import_osm")
    _run(sys.executable, "-m", "scripts.seed_game_data")
    _run(sys.executable, "-m", "scripts.build_road_graph")


if __name__ == "__main__":
    main()
