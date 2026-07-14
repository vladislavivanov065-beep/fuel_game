"""create station_upgrades table

Revision ID: 9f7a690d3903
Revises: 9116e30d444b
Create Date: 2026-07-13 13:11:18.344375

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9f7a690d3903"
down_revision: str | Sequence[str] | None = "9116e30d444b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

upgrade_type_enum = postgresql.ENUM(
    "pumps",
    "tanks",
    "shop",
    "food_court",
    "car_wash",
    "rating",
    "advertising",
    "parking",
    "loyalty_program",
    name="upgrade_type",
)
upgrade_status_enum = postgresql.ENUM(
    "under_construction", "active", "expired", name="upgrade_status"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "station_upgrades",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("game_id", sa.UUID(), nullable=False),
        sa.Column("station_id", sa.UUID(), nullable=False),
        sa.Column("upgrade_type", upgrade_type_enum, nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("status", upgrade_status_enum, nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["game_rooms.id"]),
        sa.ForeignKeyConstraint(["station_id"], ["game_stations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "station_id", "upgrade_type", name="uq_station_upgrades_station_upgrade_type"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("station_upgrades")
    upgrade_status_enum.drop(op.get_bind(), checkfirst=True)
    upgrade_type_enum.drop(op.get_bind(), checkfirst=True)
