"""create game_events table

Revision ID: 52c04a07aa04
Revises: 9f7a690d3903
Create Date: 2026-07-13 13:58:28.704656

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "52c04a07aa04"
down_revision: str | Sequence[str] | None = "9f7a690d3903"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

event_type_enum = postgresql.ENUM(
    "storm",
    "severe_storm",
    "fuel_riot",
    "economic_crisis",
    "oil_price_drop",
    "road_works",
    "city_festival",
    "tourist_season",
    "regulatory_inspection",
    "refinery_breakdown",
    name="event_type",
)
event_status_enum = postgresql.ENUM("active", "expired", name="event_status")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "game_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("game_id", sa.UUID(), nullable=False),
        sa.Column("event_type", event_type_enum, nullable=False),
        sa.Column("status", event_status_enum, nullable=False),
        sa.Column("region_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("modifiers_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["game_rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("game_events")
    event_status_enum.drop(op.get_bind(), checkfirst=True)
    event_type_enum.drop(op.get_bind(), checkfirst=True)
