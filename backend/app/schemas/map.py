import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class StationTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    osm_id: str | None
    name: str
    latitude: float
    longitude: float
    base_price: Decimal
    metadata_json: dict[str, object]


class RefineryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    latitude: float
    longitude: float


class MapDataResponse(BaseModel):
    stations: list[StationTemplateResponse]
    refineries: list[RefineryResponse]
