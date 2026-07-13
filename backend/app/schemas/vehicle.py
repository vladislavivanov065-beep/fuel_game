import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.db.models.station_fuel import FuelType
from app.db.models.vehicle import DriverType, VehicleStatus

if TYPE_CHECKING:
    from app.db.models.vehicle import Vehicle


class VehicleRoutePointResponse(BaseModel):
    latitude: float
    longitude: float
    cumulative_minutes: float


class VehicleResponse(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    driver_type: DriverType
    fuel_type: FuelType
    status: VehicleStatus
    route_progress: float
    current_latitude: float
    current_longitude: float
    route_points: list[VehicleRoutePointResponse]
    total_distance_km: float
    total_travel_time_minutes: float
    fuel_liters: Decimal
    tank_capacity_liters: Decimal
    chosen_station_id: uuid.UUID | None
    started_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, vehicle: "Vehicle") -> "VehicleResponse":
        return cls(
            id=vehicle.id,
            game_id=vehicle.game_id,
            driver_type=vehicle.driver_type,
            fuel_type=vehicle.fuel_type,
            status=vehicle.status,
            route_progress=vehicle.route_progress,
            current_latitude=vehicle.current_latitude,
            current_longitude=vehicle.current_longitude,
            route_points=[
                VehicleRoutePointResponse(
                    latitude=point["latitude"],
                    longitude=point["longitude"],
                    cumulative_minutes=point["cumulative_minutes"],
                )
                for point in vehicle.route_json["points"]
            ],
            total_distance_km=vehicle.route_json["total_distance_km"],
            total_travel_time_minutes=vehicle.route_json["total_travel_time_minutes"],
            fuel_liters=vehicle.fuel_liters,
            tank_capacity_liters=vehicle.tank_capacity_liters,
            chosen_station_id=vehicle.chosen_station_id,
            started_at=vehicle.started_at,
            updated_at=vehicle.updated_at,
        )
