"""create trade offers table

Revision ID: bc39e70bcd34
Revises: 2f9ba9f3c905
Create Date: 2026-07-17 13:18:54.415611

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "bc39e70bcd34"
down_revision: str | Sequence[str] | None = "2f9ba9f3c905"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

trade_offer_type_enum = postgresql.ENUM("station_sale", "fuel_sale", name="trade_offer_type")
trade_offer_status_enum = postgresql.ENUM(
    "pending", "accepted", "rejected", "cancelled", "expired", name="trade_offer_status"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "trade_offers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("game_id", sa.UUID(), nullable=False),
        sa.Column("seller_id", sa.UUID(), nullable=False),
        sa.Column("buyer_id", sa.UUID(), nullable=True),
        sa.Column("offer_type", trade_offer_type_enum, nullable=False),
        sa.Column("status", trade_offer_status_enum, nullable=False),
        sa.Column("terms_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["game_players.id"]),
        sa.ForeignKeyConstraint(["game_id"], ["game_rooms.id"]),
        sa.ForeignKeyConstraint(["seller_id"], ["game_players.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("trade_offers")
    trade_offer_status_enum.drop(op.get_bind(), checkfirst=True)
    trade_offer_type_enum.drop(op.get_bind(), checkfirst=True)
