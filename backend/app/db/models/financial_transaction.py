import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

TRANSACTION_TYPE_STATION_PURCHASE = "station_purchase"
TRANSACTION_TYPE_FUEL_SALE = "fuel_sale"
TRANSACTION_TYPE_FUEL_ORDER = "fuel_order"
TRANSACTION_TYPE_STATION_UPGRADE = "station_upgrade"
TRANSACTION_TYPE_ANCILLARY_REVENUE = "ancillary_revenue"
TRANSACTION_TYPE_EVENT_FINE = "event_fine"
TRANSACTION_TYPE_TRADE_STATION_SALE = "trade_station_sale"
TRANSACTION_TYPE_TRADE_FUEL_SALE = "trade_fuel_sale"


class FinancialTransaction(Base):
    __tablename__ = "financial_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_rooms.id"), nullable=False
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_players.id"), nullable=False
    )
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
