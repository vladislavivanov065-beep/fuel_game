import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.station_fuel import FuelType


class VehicleStatus(enum.StrEnum):
    DRIVING = "driving"
    REFUELING = "refueling"


class DriverType(enum.StrEnum):
    ECONOMICAL = "economical"
    HURRIED = "hurried"
    LOYAL = "loyal"
    PREMIUM = "premium"
    RANDOM = "random"


class VehicleType(enum.StrEnum):
    HATCHBACK = "hatchback"
    JEEP = "jeep"
    PICKUP = "pickup"
    MOTORCYCLE = "motorcycle"
    MARSHRUTKA = "marshrutka"
    CARGO_TRUCK = "cargo_truck"
    TROLLEYBUS = "trolleybus"
    AMBULANCE = "ambulance"
    POLICE = "police"
    FIRE_TRUCK = "fire_truck"


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_rooms.id"), nullable=False
    )
    driver_type: Mapped[DriverType] = mapped_column(
        Enum(
            DriverType,
            name="driver_type",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    vehicle_type: Mapped[VehicleType] = mapped_column(
        Enum(
            VehicleType,
            name="vehicle_type",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=VehicleType.HATCHBACK,
        nullable=False,
    )
    fuel_type: Mapped[FuelType] = mapped_column(
        Enum(
            FuelType,
            name="fuel_type",
            native_enum=True,
            create_type=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[VehicleStatus] = mapped_column(
        Enum(
            VehicleStatus,
            name="vehicle_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=VehicleStatus.DRIVING,
        nullable=False,
    )

    home_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    home_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    destination_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    destination_longitude: Mapped[float] = mapped_column(Float, nullable=False)

    route_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    route_progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    current_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    current_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    heading: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    tank_capacity_liters: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    fuel_liters: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    budget: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    price_sensitivity: Mapped[float] = mapped_column(Float, nullable=False)
    distance_sensitivity: Mapped[float] = mapped_column(Float, nullable=False)
    queue_sensitivity: Mapped[float] = mapped_column(Float, nullable=False)
    rating_sensitivity: Mapped[float] = mapped_column(Float, nullable=False)

    chosen_station_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_stations.id"), nullable=True
    )
    station_departure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
