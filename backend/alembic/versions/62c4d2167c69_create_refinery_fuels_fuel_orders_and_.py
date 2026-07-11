"""create refinery_fuels fuel_orders and fuel_order_stops tables

Revision ID: 62c4d2167c69
Revises: 31a8bcbab8cf
Create Date: 2026-07-11 19:29:38.040374

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "62c4d2167c69"
down_revision: str | Sequence[str] | None = "31a8bcbab8cf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

fuel_type_enum = postgresql.ENUM("ai92", "ai95", "diesel", name="fuel_type", create_type=False)
fuel_order_status_enum = postgresql.ENUM(
    "created",
    "paid",
    "loading",
    "in_transit",
    "partially_delivered",
    "delivered",
    "cancelled",
    "failed",
    name="fuel_order_status",
)
fuel_order_stop_status_enum = postgresql.ENUM(
    "pending", "delivered", "failed", name="fuel_order_stop_status"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "refinery_fuels",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("refinery_id", sa.UUID(), nullable=False),
        sa.Column("game_id", sa.UUID(), nullable=False),
        sa.Column("fuel_type", fuel_type_enum, nullable=False),
        sa.Column("current_liters", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("purchase_price", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("loading_speed", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["game_rooms.id"]),
        sa.ForeignKeyConstraint(["refinery_id"], ["refineries.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "refinery_id",
            "game_id",
            "fuel_type",
            name="uq_refinery_fuels_refinery_game_fuel_type",
        ),
    )
    op.create_table(
        "fuel_orders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("game_id", sa.UUID(), nullable=False),
        sa.Column("player_id", sa.UUID(), nullable=False),
        sa.Column("refinery_id", sa.UUID(), nullable=False),
        sa.Column("status", fuel_order_status_enum, nullable=False),
        sa.Column("total_cost", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("delivery_cost", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["game_rooms.id"]),
        sa.ForeignKeyConstraint(["player_id"], ["game_players.id"]),
        sa.ForeignKeyConstraint(["refinery_id"], ["refineries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "fuel_order_stops",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("fuel_order_id", sa.UUID(), nullable=False),
        sa.Column("station_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("fuel_type", fuel_type_enum, nullable=False),
        sa.Column("liters", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("delivered_liters", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", fuel_order_stop_status_enum, nullable=False),
        sa.ForeignKeyConstraint(["fuel_order_id"], ["fuel_orders.id"]),
        sa.ForeignKeyConstraint(["station_id"], ["game_stations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("fuel_order_stops")
    op.drop_table("fuel_orders")
    op.drop_table("refinery_fuels")
    fuel_order_stop_status_enum.drop(op.get_bind(), checkfirst=True)
    fuel_order_status_enum.drop(op.get_bind(), checkfirst=True)
