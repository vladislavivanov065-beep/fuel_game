"""add vehicle_type and heading to vehicles

Revision ID: c2fe5330354f
Revises: bc39e70bcd34
Create Date: 2026-07-20 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c2fe5330354f"
down_revision: str | Sequence[str] | None = "bc39e70bcd34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

vehicle_type_enum = postgresql.ENUM(
    "hatchback",
    "jeep",
    "pickup",
    "motorcycle",
    "marshrutka",
    "cargo_truck",
    "trolleybus",
    "ambulance",
    "police",
    "fire_truck",
    name="vehicle_type",
)


def upgrade() -> None:
    """Upgrade schema."""
    vehicle_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "vehicles",
        sa.Column(
            "vehicle_type",
            vehicle_type_enum,
            nullable=False,
            server_default="hatchback",
        ),
    )
    op.add_column(
        "vehicles",
        sa.Column("heading", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.alter_column("vehicles", "vehicle_type", server_default=None)
    op.alter_column("vehicles", "heading", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("vehicles", "heading")
    op.drop_column("vehicles", "vehicle_type")
    vehicle_type_enum.drop(op.get_bind(), checkfirst=True)
