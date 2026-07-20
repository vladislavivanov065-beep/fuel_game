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


class RoadNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    latitude: float
    longitude: float


class RoadEdgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_node_id: uuid.UUID
    to_node_id: uuid.UUID
    road_type: str
    is_closed: bool


class TrafficLightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    road_node_id: uuid.UUID
    red_seconds: float
    yellow_seconds: float
    green_seconds: float
    offset_seconds: float


class MapDataResponse(BaseModel):
    stations: list[StationTemplateResponse]
    refineries: list[RefineryResponse]
    road_nodes: list[RoadNodeResponse]
    road_edges: list[RoadEdgeResponse]
    traffic_lights: list[TrafficLightResponse]
