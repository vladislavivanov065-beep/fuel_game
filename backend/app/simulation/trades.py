import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trade_offer import TradeOffer, TradeOfferStatus


async def expire_due_trade_offers_for_game(db: AsyncSession, game_id: uuid.UUID) -> list[uuid.UUID]:
    """Flip PENDING -> EXPIRED for trade offers whose ``expires_at`` has passed."""
    now = datetime.now(UTC)
    due_offers = (
        (
            await db.execute(
                select(TradeOffer).where(
                    TradeOffer.game_id == game_id,
                    TradeOffer.status == TradeOfferStatus.PENDING,
                    TradeOffer.expires_at <= now,
                )
            )
        )
        .scalars()
        .all()
    )

    expired_ids: list[uuid.UUID] = []
    for offer in due_offers:
        offer.status = TradeOfferStatus.EXPIRED
        expired_ids.append(offer.id)

    if expired_ids:
        await db.commit()

    return expired_ids
