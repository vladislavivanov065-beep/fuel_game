"""create road_nodes road_edges and trucks tables

Revision ID: 8b76a08c9043
Revises: 62c4d2167c69
Create Date: 2026-07-13 07:08:03.147501

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8b76a08c9043"
down_revision: str | Sequence[str] | None = "62c4d2167c69"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

truck_status_enum = postgresql.ENUM("en_route", "delivered", name="truck_status")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "road_nodes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("osm_id", sa.String(length=64), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "road_edges",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("from_node_id", sa.UUID(), nullable=False),
        sa.Column("to_node_id", sa.UUID(), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column("max_speed_kmh", sa.Float(), nullable=False),
        sa.Column("road_type", sa.String(length=32), nullable=False),
        sa.Column("is_one_way", sa.Boolean(), nullable=False),
        sa.Column("traffic_coefficient", sa.Float(), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["from_node_id"], ["road_nodes.id"]),
        sa.ForeignKeyConstraint(["to_node_id"], ["road_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "trucks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("game_id", sa.UUID(), nullable=False),
        sa.Column("fuel_order_id", sa.UUID(), nullable=False),
        sa.Column("status", truck_status_enum, nullable=False),
        sa.Column("route_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("route_progress", sa.Float(), nullable=False),
        sa.Column("current_latitude", sa.Float(), nullable=False),
        sa.Column("current_longitude", sa.Float(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["fuel_order_id"], ["fuel_orders.id"]),
        sa.ForeignKeyConstraint(["game_id"], ["game_rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("trucks")
    op.drop_table("road_edges")
    op.drop_table("road_nodes")
    truck_status_enum.drop(op.get_bind(), checkfirst=True)
