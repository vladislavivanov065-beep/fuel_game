from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.games import router as games_router
from app.api.health import router as health_router
from app.api.map import router as map_router
from app.core.config import get_settings
from app.websocket.game_ws import router as game_ws_router

settings = get_settings()

app = FastAPI(title=settings.app_name)

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
app.include_router(map_router)
app.include_router(game_ws_router)
