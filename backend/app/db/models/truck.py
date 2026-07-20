import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TruckStatus(enum.StrEnum):
    EN_ROUTE = "en_route"
    DELIVERED = "delivered"


class Truck(Base):
    __tablename__ = "trucks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_rooms.id"), nullable=False
    )
    fuel_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fuel_orders.id"), nullable=False
    )
    status: Mapped[TruckStatus] = mapped_column(
        Enum(
            TruckStatus,
            name="truck_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=TruckStatus.EN_ROUTE,
        nullable=False,
    )
    route_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    route_progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    current_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    current_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    heading: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Physical simulation state (Этап 14.3) — see Vehicle.route_edge_index for
    # why this index is needed alongside current_edge_id.
    route_edge_index: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_edge_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("road_edges.id"), nullable=True
    )
    position_on_edge_m: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    velocity_kmh: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
