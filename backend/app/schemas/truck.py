import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.db.models.truck import TruckStatus

if TYPE_CHECKING:
    from app.db.models.truck import Truck


class TruckRoutePointResponse(BaseModel):
    latitude: float
    longitude: float
    cumulative_minutes: float


class TruckResponse(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    fuel_order_id: uuid.UUID
    status: TruckStatus
    route_progress: float
    current_latitude: float
    current_longitude: float
    heading: float
    route_points: list[TruckRoutePointResponse]
    total_distance_km: float
    total_travel_time_minutes: float
    started_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, truck: "Truck") -> "TruckResponse":
        return cls(
            id=truck.id,
            game_id=truck.game_id,
            fuel_order_id=truck.fuel_order_id,
            status=truck.status,
            route_progress=truck.route_progress,
            current_latitude=truck.current_latitude,
            current_longitude=truck.current_longitude,
            heading=truck.heading,
            route_points=[
                TruckRoutePointResponse(
                    latitude=point["latitude"],
                    longitude=point["longitude"],
                    cumulative_minutes=point["cumulative_minutes"],
                )
                for point in truck.route_json["points"]
            ],
            total_distance_km=truck.route_json["total_distance_km"],
            total_travel_time_minutes=truck.route_json["total_travel_time_minutes"],
            started_at=truck.started_at,
            updated_at=truck.updated_at,
        )
