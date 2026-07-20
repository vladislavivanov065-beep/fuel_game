from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_current_user
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.map import (
    MapDataResponse,
    RefineryResponse,
    RoadEdgeResponse,
    RoadNodeResponse,
    StationTemplateResponse,
    TrafficLightResponse,
)
from app.services.map_service import (
    list_road_edges,
    list_road_nodes,
    list_station_templates,
    list_traffic_lights,
)
from app.services.refinery_service import list_refineries

router = APIRouter(prefix="/api/map", tags=["map"])


@router.get("", response_model=MapDataResponse)
async def get_map_data(
    _user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MapDataResponse:
    stations = await list_station_templates(db)
    refineries = await list_refineries(db)
    road_nodes = await list_road_nodes(db)
    road_edges = await list_road_edges(db)
    traffic_lights = await list_traffic_lights(db)
    return MapDataResponse(
        stations=[StationTemplateResponse.model_validate(s) for s in stations],
        refineries=[RefineryResponse.model_validate(r) for r in refineries],
        road_nodes=[RoadNodeResponse.model_validate(n) for n in road_nodes],
        road_edges=[RoadEdgeResponse.model_validate(e) for e in road_edges],
        traffic_lights=[TrafficLightResponse.model_validate(t) for t in traffic_lights],
    )
