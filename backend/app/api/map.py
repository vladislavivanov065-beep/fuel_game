from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_current_user
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.map import MapDataResponse, RefineryResponse, StationTemplateResponse
from app.services.map_service import list_station_templates
from app.services.refinery_service import list_refineries

router = APIRouter(prefix="/api/map", tags=["map"])


@router.get("", response_model=MapDataResponse)
async def get_map_data(
    _user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MapDataResponse:
    stations = await list_station_templates(db)
    refineries = await list_refineries(db)
    return MapDataResponse(
        stations=[StationTemplateResponse.model_validate(s) for s in stations],
        refineries=[RefineryResponse.model_validate(r) for r in refineries],
    )
