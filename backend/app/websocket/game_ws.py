import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.services.auth_service import get_current_user
from app.services.game_service import GameNotFoundError, NotAGameMemberError, get_game_for_member
from app.websocket.connection_manager import connection_manager

settings = get_settings()

router = APIRouter()


@router.websocket("/ws/games/{game_id}")
async def game_websocket(websocket: WebSocket, game_id: uuid.UUID) -> None:
    session_token = websocket.cookies.get(settings.session_cookie_name)

    async with async_session_factory() as db:
        user = await get_current_user(db, session_token)
        if user is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        try:
            await get_game_for_member(db, game_id, user.id)
        except (GameNotFoundError, NotAGameMemberError):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await connection_manager.connect(game_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        connection_manager.disconnect(game_id, websocket)
