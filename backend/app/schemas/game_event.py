import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from app.db.models.game_event import EventStatus, EventType

if TYPE_CHECKING:
    from app.db.models.game_event import GameEvent


class TriggerEventRequest(BaseModel):
    event_type: EventType


class GameEventResponse(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    event_type: EventType
    status: EventStatus
    region: dict[str, Any] | None
    modifiers: dict[str, Any]
    started_at: datetime
    ends_at: datetime

    @classmethod
    def from_model(cls, event: "GameEvent") -> "GameEventResponse":
        return cls(
            id=event.id,
            game_id=event.game_id,
            event_type=event.event_type,
            status=event.status,
            region=event.region_json,
            modifiers=event.modifiers_json,
            started_at=event.started_at,
            ends_at=event.ends_at,
        )
