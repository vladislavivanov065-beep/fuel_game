"""create road accidents table

Revision ID: 786ca269b31c
Revises: 27ab1ad5d891
Create Date: 2026-07-20 10:07:51.013935

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "786ca269b31c"
down_revision: str | Sequence[str] | None = "27ab1ad5d891"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

accident_severity_enum = postgresql.ENUM("minor", "major", name="accident_severity")


def upgrade() -> None:
    """Upgrade schema."""
    accident_severity_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "road_accidents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("game_id", sa.UUID(), nullable=False),
        sa.Column("road_edge_id", sa.UUID(), nullable=False),
        sa.Column(
            "severity",
            postgresql.ENUM("minor", "major", name="accident_severity", create_type=False),
            nullable=False,
        ),
        sa.Column("previous_traffic_coefficient", sa.Float(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["game_rooms.id"]),
        sa.ForeignKeyConstraint(["road_edge_id"], ["road_edges.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("road_accidents")
    accident_severity_enum.drop(op.get_bind(), checkfirst=True)
