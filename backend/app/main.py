from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.events import router as events_router
from app.api.fuel_orders import router as fuel_orders_router
from app.api.games import router as games_router
from app.api.health import router as health_router
from app.api.map import router as map_router
from app.api.stations import router as stations_router
from app.api.vehicles import router as vehicles_router
from app.core.config import get_settings
from app.core.release import run_release_tasks
from app.simulation import scheduler
from app.websocket.game_ws import router as game_ws_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await run_release_tasks()
    scheduler.start()
    yield
    await scheduler.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(games_router)
app.include_router(stations_router)
app.include_router(map_router)
app.include_router(fuel_orders_router)
app.include_router(vehicles_router)
app.include_router(events_router)
app.include_router(game_ws_router)
