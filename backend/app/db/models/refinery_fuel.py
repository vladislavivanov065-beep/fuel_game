import uuid
from decimal import Decimal

from sqlalchemy import Enum, Float, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.station_fuel import FuelType


class RefineryFuel(Base):
    __tablename__ = "refinery_fuels"
    __table_args__ = (
        UniqueConstraint(
            "refinery_id", "game_id", "fuel_type", name="uq_refinery_fuels_refinery_game_fuel_type"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    refinery_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refineries.id"), nullable=False
    )
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_rooms.id"), nullable=False
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
    current_liters: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    loading_speed: Mapped[float] = mapped_column(Float, nullable=False)
