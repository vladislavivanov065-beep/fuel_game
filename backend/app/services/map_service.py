from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode
from app.db.models.station_template import StationTemplate
from app.db.models.traffic_light import TrafficLight


async def list_station_templates(db: AsyncSession) -> list[StationTemplate]:
    result = await db.execute(select(StationTemplate).order_by(StationTemplate.name))
    return list(result.scalars())


async def list_road_nodes(db: AsyncSession) -> list[RoadNode]:
    return list((await db.execute(select(RoadNode))).scalars())


async def list_road_edges(db: AsyncSession) -> list[RoadEdge]:
    return list((await db.execute(select(RoadEdge))).scalars())


async def list_traffic_lights(db: AsyncSession) -> list[TrafficLight]:
    return list((await db.execute(select(TrafficLight))).scalars())
