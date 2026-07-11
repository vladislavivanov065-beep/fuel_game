import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.db.models.fuel_order import FuelOrderStatus
from app.db.models.fuel_order_stop import FuelOrderStopStatus
from app.db.models.station_fuel import FuelType

if TYPE_CHECKING:
    from app.db.models.fuel_order import FuelOrder
    from app.db.models.fuel_order_stop import FuelOrderStop
    from app.db.models.refinery_fuel import RefineryFuel
    from app.services.refinery_service import RefineryWithFuels


class CreateFuelOrderRequest(BaseModel):
    refinery_id: uuid.UUID
    station_id: uuid.UUID
    fuel_type: FuelType
    liters: Decimal = Field(gt=0)


class RefineryFuelResponse(BaseModel):
    fuel_type: FuelType
    current_liters: Decimal
    purchase_price: Decimal
    loading_speed: float

    @classmethod
    def from_model(cls, fuel: "RefineryFuel") -> "RefineryFuelResponse":
        return cls(
            fuel_type=fuel.fuel_type,
            current_liters=fuel.current_liters,
            purchase_price=fuel.purchase_price,
            loading_speed=fuel.loading_speed,
        )


class RefineryWithFuelsResponse(BaseModel):
    id: uuid.UUID
    name: str
    latitude: float
    longitude: float
    fuels: list[RefineryFuelResponse]

    @classmethod
    def from_model(cls, item: "RefineryWithFuels") -> "RefineryWithFuelsResponse":
        return cls(
            id=item.refinery.id,
            name=item.refinery.name,
            latitude=item.refinery.latitude,
            longitude=item.refinery.longitude,
            fuels=[RefineryFuelResponse.from_model(fuel) for fuel in item.fuels],
        )


class FuelOrderStopResponse(BaseModel):
    station_id: uuid.UUID
    position: int
    fuel_type: FuelType
    liters: Decimal
    delivered_liters: Decimal
    status: FuelOrderStopStatus

    @classmethod
    def from_model(cls, stop: "FuelOrderStop") -> "FuelOrderStopResponse":
        return cls(
            station_id=stop.station_id,
            position=stop.position,
            fuel_type=stop.fuel_type,
            liters=stop.liters,
            delivered_liters=stop.delivered_liters,
            status=stop.status,
        )


class FuelOrderResponse(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    player_id: uuid.UUID
    refinery_id: uuid.UUID
    status: FuelOrderStatus
    total_cost: Decimal
    delivery_cost: Decimal
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    stops: list[FuelOrderStopResponse]

    @classmethod
    def from_model(cls, order: "FuelOrder") -> "FuelOrderResponse":
        return cls(
            id=order.id,
            game_id=order.game_id,
            player_id=order.player_id,
            refinery_id=order.refinery_id,
            status=order.status,
            total_cost=order.total_cost,
            delivery_cost=order.delivery_cost,
            created_at=order.created_at,
            started_at=order.started_at,
            completed_at=order.completed_at,
            stops=[FuelOrderStopResponse.from_model(stop) for stop in order.stops],
        )
