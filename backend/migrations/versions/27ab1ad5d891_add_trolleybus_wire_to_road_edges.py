"""add trolleybus_wire to road_edges

Revision ID: 27ab1ad5d891
Revises: bd4351233f09
Create Date: 2026-07-20 00:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "27ab1ad5d891"
down_revision: str | Sequence[str] | None = "bd4351233f09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "road_edges",
        sa.Column("trolleybus_wire", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.alter_column("road_edges", "trolleybus_wire", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("road_edges", "trolleybus_wire")
