import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventType(enum.StrEnum):
    STORM = "storm"
    SEVERE_STORM = "severe_storm"
    FUEL_RIOT = "fuel_riot"
    ECONOMIC_CRISIS = "economic_crisis"
    OIL_PRICE_DROP = "oil_price_drop"
    ROAD_WORKS = "road_works"
    CITY_FESTIVAL = "city_festival"
    TOURIST_SEASON = "tourist_season"
    REGULATORY_INSPECTION = "regulatory_inspection"
    REFINERY_BREAKDOWN = "refinery_breakdown"


class EventStatus(enum.StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"


class GameEvent(Base):
    __tablename__ = "game_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_rooms.id"), nullable=False
    )
    event_type: Mapped[EventType] = mapped_column(
        Enum(
            EventType,
            name="event_type",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[EventStatus] = mapped_column(
        Enum(
            EventStatus,
            name="event_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=EventStatus.ACTIVE,
        nullable=False,
    )
    region_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    modifiers_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
