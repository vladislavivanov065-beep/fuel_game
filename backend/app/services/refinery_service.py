from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.refinery import Refinery


async def ensure_refinery(
    db: AsyncSession, name: str, latitude: float, longitude: float
) -> Refinery:
    existing = (
        await db.execute(select(Refinery).where(Refinery.name == name))
    ).scalar_one_or_none()
    if existing is not None:
        existing.latitude = latitude
        existing.longitude = longitude
        await db.commit()
        await db.refresh(existing)
        return existing

    refinery = Refinery(name=name, latitude=latitude, longitude=longitude)
    db.add(refinery)
    await db.commit()
    await db.refresh(refinery)
    return refinery


async def list_refineries(db: AsyncSession) -> list[Refinery]:
    result = await db.execute(select(Refinery).order_by(Refinery.name))
    return list(result.scalars())
