import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccidentSeverity(enum.StrEnum):
    MINOR = "minor"
    MAJOR = "major"


class RoadAccident(Base):
    """A traffic accident on a road edge (Этап 14.5).

    Deliberately independent of ``GameEvent``: risk is rolled every tick from
    an edge's own congestion (see ``simulation/accidents.py``), not triggered
    manually or by the event scheduler. MINOR raises ``RoadEdge.
    traffic_coefficient`` (slower, still passable); MAJOR sets ``RoadEdge.
    is_closed`` (reusing the same closure mechanism ``road_works`` uses, so
    truck rerouting reacts to it with no new code). ``previous_
    traffic_coefficient`` lets a MINOR accident's penalty be reverted
    exactly on expiry instead of resetting to a hardcoded 1.0.
    """

    __tablename__ = "road_accidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_rooms.id"), nullable=False
    )
    road_edge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("road_edges.id"), nullable=False
    )
    severity: Mapped[AccidentSeverity] = mapped_column(
        Enum(
            AccidentSeverity,
            name="accident_severity",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    previous_traffic_coefficient: Mapped[float] = mapped_column(Float, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
