from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.health import HealthResponse
from app.services.health_service import check_health

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
async def health(db: Annotated[AsyncSession, Depends(get_db_session)]) -> HealthResponse:
    return await check_health(db)
