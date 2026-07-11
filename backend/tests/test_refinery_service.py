from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.refinery import Refinery
from app.services.refinery_service import ensure_refinery, list_refineries


async def test_ensure_refinery_creates_one_row(db_session: AsyncSession) -> None:
    refinery = await ensure_refinery(db_session, "Test Depot", 56.7, 47.9)

    assert refinery.name == "Test Depot"
    result = await db_session.execute(select(Refinery).where(Refinery.name == "Test Depot"))
    assert len(result.scalars().all()) == 1


async def test_ensure_refinery_is_idempotent(db_session: AsyncSession) -> None:
    await ensure_refinery(db_session, "Idempotent Depot", 56.7, 47.9)
    await ensure_refinery(db_session, "Idempotent Depot", 56.8, 48.0)

    result = await db_session.execute(select(Refinery).where(Refinery.name == "Idempotent Depot"))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].latitude == 56.8
    assert rows[0].longitude == 48.0


async def test_list_refineries_returns_all(db_session: AsyncSession) -> None:
    await ensure_refinery(db_session, "Depot A", 56.0, 47.0)
    await ensure_refinery(db_session, "Depot B", 57.0, 48.0)

    refineries = await list_refineries(db_session)

    names = {r.name for r in refineries}
    assert names == {"Depot A", "Depot B"}
