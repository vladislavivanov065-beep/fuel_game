"""Seed the single game refinery (fuel depot) for the MVP.

Idempotent: re-running this script updates the existing refinery's
coordinates instead of creating a duplicate.

Usage:
    python -m scripts.seed_game_data
"""

import asyncio

from app.db.session import async_session_factory
from app.services.refinery_service import ensure_refinery

REFINERY_NAME = "Нефтебаза Йошкар-Ола"
REFINERY_LATITUDE = 56.7010
REFINERY_LONGITUDE = 47.9520


async def main() -> None:
    async with async_session_factory() as db:
        refinery = await ensure_refinery(db, REFINERY_NAME, REFINERY_LATITUDE, REFINERY_LONGITUDE)

    print(f"Refinery ready: {refinery.name} ({refinery.latitude}, {refinery.longitude})")


if __name__ == "__main__":
    asyncio.run(main())
