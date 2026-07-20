import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RoadEdge(Base):
    """A directed road segment between two graph vertices.

    Two-way roads are represented as a pair of RoadEdge rows (one per
    direction) so the routing algorithm only ever deals with directed edges.
    """

    __tablename__ = "road_edges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("road_nodes.id"), nullable=False
    )
    to_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("road_nodes.id"), nullable=False
    )
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    max_speed_kmh: Mapped[float] = mapped_column(Float, nullable=False)
    road_type: Mapped[str] = mapped_column(String(32), nullable=False)
    is_one_way: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    traffic_coefficient: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trolleybus_wire: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
