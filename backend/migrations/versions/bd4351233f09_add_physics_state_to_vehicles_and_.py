"""add physics state to vehicles and trucks

Revision ID: bd4351233f09
Revises: 1b99e1f96348
Create Date: 2026-07-20 00:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bd4351233f09"
down_revision: str | Sequence[str] | None = "1b99e1f96348"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "vehicles",
        sa.Column("route_edge_index", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("vehicles", sa.Column("current_edge_id", sa.UUID(), nullable=True))
    op.add_column(
        "vehicles",
        sa.Column("position_on_edge_m", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.add_column(
        "vehicles", sa.Column("velocity_kmh", sa.Float(), nullable=False, server_default="0.0")
    )
    op.create_foreign_key(
        "fk_vehicles_current_edge_id_road_edges",
        "vehicles",
        "road_edges",
        ["current_edge_id"],
        ["id"],
    )
    op.alter_column("vehicles", "route_edge_index", server_default=None)
    op.alter_column("vehicles", "position_on_edge_m", server_default=None)
    op.alter_column("vehicles", "velocity_kmh", server_default=None)

    op.add_column("trucks", sa.Column("heading", sa.Float(), nullable=False, server_default="0.0"))
    op.add_column(
        "trucks",
        sa.Column("route_edge_index", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("trucks", sa.Column("current_edge_id", sa.UUID(), nullable=True))
    op.add_column(
        "trucks",
        sa.Column("position_on_edge_m", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.add_column(
        "trucks", sa.Column("velocity_kmh", sa.Float(), nullable=False, server_default="0.0")
    )
    op.create_foreign_key(
        "fk_trucks_current_edge_id_road_edges", "trucks", "road_edges", ["current_edge_id"], ["id"]
    )
    op.alter_column("trucks", "heading", server_default=None)
    op.alter_column("trucks", "route_edge_index", server_default=None)
    op.alter_column("trucks", "position_on_edge_m", server_default=None)
    op.alter_column("trucks", "velocity_kmh", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_trucks_current_edge_id_road_edges", "trucks", type_="foreignkey")
    op.drop_column("trucks", "velocity_kmh")
    op.drop_column("trucks", "position_on_edge_m")
    op.drop_column("trucks", "current_edge_id")
    op.drop_column("trucks", "route_edge_index")
    op.drop_column("trucks", "heading")

    op.drop_constraint("fk_vehicles_current_edge_id_road_edges", "vehicles", type_="foreignkey")
    op.drop_column("vehicles", "velocity_kmh")
    op.drop_column("vehicles", "position_on_edge_m")
    op.drop_column("vehicles", "current_edge_id")
    op.drop_column("vehicles", "route_edge_index")
