"""create traffic_lights table

Revision ID: 1b99e1f96348
Revises: c2fe5330354f
Create Date: 2026-07-20 00:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1b99e1f96348"
down_revision: str | Sequence[str] | None = "c2fe5330354f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "traffic_lights",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("road_node_id", sa.UUID(), nullable=False),
        sa.Column("red_seconds", sa.Float(), nullable=False),
        sa.Column("yellow_seconds", sa.Float(), nullable=False),
        sa.Column("green_seconds", sa.Float(), nullable=False),
        sa.Column("offset_seconds", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["road_node_id"], ["road_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("road_node_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("traffic_lights")
