from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.station_template import StationTemplate


async def list_station_templates(db: AsyncSession) -> list[StationTemplate]:
    result = await db.execute(select(StationTemplate).order_by(StationTemplate.name))
    return list(result.scalars())
