"""Manually run migrations and seed static map data.

The same logic (app.core.release.run_release_tasks) also runs automatically
on every app startup, so this standalone entrypoint mainly exists for
re-running it locally without restarting the app. Idempotent.

Usage:
    python -m scripts.release
"""

import asyncio

from app.core.release import run_release_tasks


def main() -> None:
    asyncio.run(run_release_tasks())


if __name__ == "__main__":
    main()
