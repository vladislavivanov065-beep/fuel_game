import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = {}

    async def connect(self, game_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(game_id, set()).add(websocket)

    def disconnect(self, game_id: uuid.UUID, websocket: WebSocket) -> None:
        connections = self._connections.get(game_id)
        if connections is None:
            return

        connections.discard(websocket)
        if not connections:
            del self._connections[game_id]

    async def broadcast(self, game_id: uuid.UUID, event_type: str, data: dict[str, Any]) -> None:
        connections = self._connections.get(game_id)
        if not connections:
            return

        message = {
            "event": event_type,
            "event_id": str(uuid.uuid4()),
            "server_time": datetime.now(UTC).isoformat(),
            "game_id": str(game_id),
            "data": data,
        }
        payload = json.dumps(message)

        dead_connections: list[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_text(payload)
            except Exception:
                # A broken socket must not stop delivery to the rest of the room.
                dead_connections.append(connection)

        for connection in dead_connections:
            connections.discard(connection)


connection_manager = ConnectionManager()
