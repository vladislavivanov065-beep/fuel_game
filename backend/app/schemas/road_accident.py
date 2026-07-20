import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.db.models.road_accident import AccidentSeverity

if TYPE_CHECKING:
    from app.db.models.road_accident import RoadAccident


class RoadAccidentResponse(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    road_edge_id: uuid.UUID
    severity: AccidentSeverity
    started_at: datetime
    ends_at: datetime

    @classmethod
    def from_model(cls, accident: "RoadAccident") -> "RoadAccidentResponse":
        return cls(
            id=accident.id,
            game_id=accident.game_id,
            road_edge_id=accident.road_edge_id,
            severity=accident.severity,
            started_at=accident.started_at,
            ends_at=accident.ends_at,
        )
