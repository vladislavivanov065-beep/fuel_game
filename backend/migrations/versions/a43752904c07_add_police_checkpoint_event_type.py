"""add police_checkpoint event type

Revision ID: a43752904c07
Revises: 786ca269b31c
Create Date: 2026-07-20 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a43752904c07"
down_revision: str | Sequence[str] | None = "786ca269b31c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ORIGINAL_VALUES = (
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
)
_NEW_VALUE = "police_checkpoint"


def upgrade() -> None:
    """Upgrade schema."""
    # Postgres allows ALTER TYPE ... ADD VALUE inside a transaction (PG12+),
    # as long as the new value isn't used in the same transaction — which it
    # isn't here.
    op.execute(f"ALTER TYPE event_type ADD VALUE '{_NEW_VALUE}'")


def downgrade() -> None:
    """Downgrade schema.

    Postgres has no ``DROP VALUE`` for enums, so the type is rebuilt from
    scratch without the new value. This only succeeds if no ``game_events``
    row currently uses it.
    """
    op.execute("ALTER TABLE game_events ALTER COLUMN event_type TYPE text")
    op.execute("DROP TYPE event_type")
    restored_enum = postgresql.ENUM(*_ORIGINAL_VALUES, name="event_type")
    restored_enum.create(op.get_bind(), checkfirst=True)
    op.execute(
        "ALTER TABLE game_events ALTER COLUMN event_type "
        "TYPE event_type USING event_type::event_type"
    )
