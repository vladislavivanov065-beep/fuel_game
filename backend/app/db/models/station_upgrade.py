import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UpgradeType(enum.StrEnum):
    PUMPS = "pumps"
    TANKS = "tanks"
    SHOP = "shop"
    FOOD_COURT = "food_court"
    CAR_WASH = "car_wash"
    RATING = "rating"
    ADVERTISING = "advertising"
    PARKING = "parking"
    LOYALTY_PROGRAM = "loyalty_program"


class UpgradeStatus(enum.StrEnum):
    UNDER_CONSTRUCTION = "under_construction"
    ACTIVE = "active"
    EXPIRED = "expired"


class StationUpgrade(Base):
    __tablename__ = "station_upgrades"
    __table_args__ = (
        UniqueConstraint(
            "station_id", "upgrade_type", name="uq_station_upgrades_station_upgrade_type"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_rooms.id"), nullable=False
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_stations.id"), nullable=False
    )
    upgrade_type: Mapped[UpgradeType] = mapped_column(
        Enum(
            UpgradeType,
            name="upgrade_type",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[UpgradeStatus] = mapped_column(
        Enum(
            UpgradeStatus,
            name="upgrade_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=UpgradeStatus.UNDER_CONSTRUCTION,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
