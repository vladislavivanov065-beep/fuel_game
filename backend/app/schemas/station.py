import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.db.models.station_fuel import FuelType

if TYPE_CHECKING:
    from app.db.models.game_station import GameStation
    from app.db.models.station_fuel import StationFuel


class SetStationPriceRequest(BaseModel):
    fuel_type: FuelType
    retail_price: Decimal = Field(gt=0)


class SetNetworkPriceRequest(BaseModel):
    fuel_type: FuelType
    retail_price: Decimal = Field(gt=0)


class StationFuelResponse(BaseModel):
    id: uuid.UUID
    fuel_type: FuelType
    current_liters: Decimal
    reserved_liters: Decimal
    capacity_liters: Decimal
    retail_price: Decimal
    average_purchase_price: Decimal
    price_updated_at: datetime | None

    @classmethod
    def from_model(cls, fuel: "StationFuel") -> "StationFuelResponse":
        return cls(
            id=fuel.id,
            fuel_type=fuel.fuel_type,
            current_liters=fuel.current_liters,
            reserved_liters=fuel.reserved_liters,
            capacity_liters=fuel.capacity_liters,
            retail_price=fuel.retail_price,
            average_purchase_price=fuel.average_purchase_price,
            price_updated_at=fuel.price_updated_at,
        )


class GameStationResponse(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    station_template_id: uuid.UUID
    name: str
    latitude: float
    longitude: float
    owner_player_id: uuid.UUID | None
    owner_display_name: str | None
    owner_network_name: str | None
    owner_network_color: str | None
    purchase_price: Decimal
    status: str
    level: int
    rating: float
    queue_length: int
    created_at: datetime
    fuels: list[StationFuelResponse]

    @classmethod
    def from_model(cls, station: "GameStation") -> "GameStationResponse":
        owner = station.owner
        return cls(
            id=station.id,
            game_id=station.game_id,
            station_template_id=station.station_template_id,
            name=station.station_template.name,
            latitude=station.station_template.latitude,
            longitude=station.station_template.longitude,
            owner_player_id=station.owner_player_id,
            owner_display_name=owner.user.display_name if owner else None,
            owner_network_name=owner.network_name if owner else None,
            owner_network_color=owner.network_color if owner else None,
            purchase_price=station.purchase_price,
            status=station.status,
            level=station.level,
            rating=station.rating,
            queue_length=station.queue_length,
            created_at=station.created_at,
            fuels=[StationFuelResponse.from_model(fuel) for fuel in station.fuels],
        )
