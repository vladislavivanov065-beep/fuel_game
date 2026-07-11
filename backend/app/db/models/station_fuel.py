import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FuelType(enum.StrEnum):
    AI92 = "ai92"
    AI95 = "ai95"
    DIESEL = "diesel"


class StationFuel(Base):
    __tablename__ = "station_fuels"
    __table_args__ = (
        UniqueConstraint("game_station_id", "fuel_type", name="uq_station_fuels_station_fuel_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_stations.id"), nullable=False
    )
    fuel_type: Mapped[FuelType] = mapped_column(
        Enum(
            FuelType,
            name="fuel_type",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    current_liters: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    reserved_liters: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    capacity_liters: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    retail_price: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    average_purchase_price: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), default=Decimal("0"), nullable=False
    )
    price_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
