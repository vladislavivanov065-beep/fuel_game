import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.db.models.station_fuel import FuelType
from app.db.models.trade_offer import TradeOfferStatus, TradeOfferType

if TYPE_CHECKING:
    from app.db.models.trade_offer import TradeOffer


class StationSaleTerms(BaseModel):
    station_id: uuid.UUID
    price: Decimal = Field(gt=0)


class FuelSaleTerms(BaseModel):
    station_id: uuid.UUID
    fuel_type: FuelType
    liters: Decimal = Field(gt=0)
    price_per_liter: Decimal = Field(gt=0)


class CreateTradeOfferRequest(BaseModel):
    offer_type: TradeOfferType
    terms: dict[str, object]
    buyer_user_id: uuid.UUID | None = None
    expires_in_minutes: int = Field(default=60, gt=0, le=24 * 60)


class CounterTradeOfferRequest(BaseModel):
    terms: dict[str, object]
    expires_in_minutes: int = Field(default=60, gt=0, le=24 * 60)


class AcceptTradeOfferRequest(BaseModel):
    buyer_station_id: uuid.UUID | None = None


class TradeOfferResponse(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    seller_id: uuid.UUID
    buyer_id: uuid.UUID | None
    offer_type: TradeOfferType
    status: TradeOfferStatus
    terms: dict[str, object]
    expires_at: datetime
    created_at: datetime

    @classmethod
    def from_model(cls, offer: "TradeOffer") -> "TradeOfferResponse":
        return cls(
            id=offer.id,
            game_id=offer.game_id,
            seller_id=offer.seller_id,
            buyer_id=offer.buyer_id,
            offer_type=offer.offer_type,
            status=offer.status,
            terms=offer.terms_json,
            expires_at=offer.expires_at,
            created_at=offer.created_at,
        )
