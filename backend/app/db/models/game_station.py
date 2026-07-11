import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.game_player import GamePlayer
    from app.db.models.station_fuel import StationFuel
    from app.db.models.station_template import StationTemplate

STATION_STATUS_ACTIVE = "active"
STATION_STATUS_INACTIVE = "inactive"


class GameStation(Base):
    __tablename__ = "game_stations"
    __table_args__ = (
        UniqueConstraint("game_id", "station_template_id", name="uq_game_stations_game_template"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_rooms.id"), nullable=False
    )
    station_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("station_templates.id"), nullable=False
    )
    owner_player_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_players.id"), nullable=True
    )
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=STATION_STATUS_ACTIVE, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    rating: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    queue_length: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    station_template: Mapped["StationTemplate"] = relationship()
    owner: Mapped["GamePlayer | None"] = relationship()
    fuels: Mapped[list["StationFuel"]] = relationship()
