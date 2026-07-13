"""create vehicles table

Revision ID: 9116e30d444b
Revises: 8b76a08c9043
Create Date: 2026-07-13 08:07:14.353812

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9116e30d444b"
down_revision: str | Sequence[str] | None = "8b76a08c9043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

driver_type_enum = postgresql.ENUM(
    "economical", "hurried", "loyal", "premium", "random", name="driver_type"
)
vehicle_status_enum = postgresql.ENUM("driving", "refueling", name="vehicle_status")
fuel_type_enum = postgresql.ENUM("ai92", "ai95", "diesel", name="fuel_type", create_type=False)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "vehicles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("game_id", sa.UUID(), nullable=False),
        sa.Column("driver_type", driver_type_enum, nullable=False),
        sa.Column("fuel_type", fuel_type_enum, nullable=False),
        sa.Column("status", vehicle_status_enum, nullable=False),
        sa.Column("home_latitude", sa.Float(), nullable=False),
        sa.Column("home_longitude", sa.Float(), nullable=False),
        sa.Column("destination_latitude", sa.Float(), nullable=False),
        sa.Column("destination_longitude", sa.Float(), nullable=False),
        sa.Column("route_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("route_progress", sa.Float(), nullable=False),
        sa.Column("current_latitude", sa.Float(), nullable=False),
        sa.Column("current_longitude", sa.Float(), nullable=False),
        sa.Column("tank_capacity_liters", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("fuel_liters", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("budget", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("price_sensitivity", sa.Float(), nullable=False),
        sa.Column("distance_sensitivity", sa.Float(), nullable=False),
        sa.Column("queue_sensitivity", sa.Float(), nullable=False),
        sa.Column("rating_sensitivity", sa.Float(), nullable=False),
        sa.Column("chosen_station_id", sa.UUID(), nullable=True),
        sa.Column("station_departure_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["chosen_station_id"], ["game_stations.id"]),
        sa.ForeignKeyConstraint(["game_id"], ["game_rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("vehicles")
    vehicle_status_enum.drop(op.get_bind(), checkfirst=True)
    driver_type_enum.drop(op.get_bind(), checkfirst=True)
