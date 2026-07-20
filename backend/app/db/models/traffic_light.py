import uuid

from sqlalchemy import Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TrafficLight(Base):
    """A fixed-cycle traffic light at a road-graph intersection (Этап 14.2).

    One shared cycle per node (no per-direction phases — see Этап 14 known
    simplifications): red+yellow -> whole intersection stops, green -> whole
    intersection goes. Seeded once per node at road-graph build time
    (build_road_graph.py), not per-game — this is static map data like
    RoadEdge.max_speed_kmh, not a settings_json-configurable gameplay
    coefficient.
    """

    __tablename__ = "traffic_lights"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    road_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("road_nodes.id"), nullable=False, unique=True
    )
    red_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    yellow_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    green_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    offset_seconds: Mapped[float] = mapped_column(Float, nullable=False)
