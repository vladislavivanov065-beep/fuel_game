import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_current_user
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.trade import (
    AcceptTradeOfferRequest,
    CounterTradeOfferRequest,
    CreateTradeOfferRequest,
    TradeOfferResponse,
)
from app.services import trade_service
from app.websocket.connection_manager import connection_manager

router = APIRouter(prefix="/api/games/{game_id}/trades", tags=["trades"])


def _map_common_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, trade_service.GameNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    if isinstance(exc, trade_service.GameNotRunningError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Game is not running")
    if isinstance(exc, trade_service.NotAGameMemberError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        )
    if isinstance(exc, trade_service.TradingDisabledError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Trading is disabled in this game"
        )
    if isinstance(exc, trade_service.TradeOfferNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade offer not found")
    if isinstance(exc, trade_service.TradeOfferNotPendingError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This trade offer is no longer pending"
        )
    if isinstance(exc, trade_service.NotAuthorizedForTradeError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You cannot act on this trade offer"
        )
    if isinstance(exc, trade_service.CannotTradeWithSelfError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Cannot trade with yourself"
        )
    if isinstance(exc, trade_service.StationNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found")
    if isinstance(exc, trade_service.StationNotOwnedByPlayerError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Station is not owned by that player"
        )
    if isinstance(exc, trade_service.StationAlreadyListedError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This station already has a pending sale offer",
        )
    if isinstance(exc, trade_service.FuelTypeNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel type not found")
    if isinstance(exc, trade_service.InsufficientFuelError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Not enough fuel in stock"
        )
    if isinstance(exc, trade_service.InsufficientCapacityError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Not enough tank capacity"
        )
    if isinstance(exc, trade_service.InsufficientFundsError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Insufficient funds")
    if isinstance(exc, trade_service.BuyerStationRequiredError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="buyer_station_id is required to accept a fuel sale offer",
        )
    if isinstance(exc, trade_service.TradeOfferNotTargetedError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a targeted offer can be countered",
        )
    if isinstance(exc, trade_service.InvalidCounterTermsError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Counter-offer must target the same asset",
        )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("", response_model=list[TradeOfferResponse])
async def list_trades(
    game_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[TradeOfferResponse]:
    try:
        offers = await trade_service.list_trade_offers(db, game_id, user.id)
    except Exception as exc:
        raise _map_common_errors(exc) from exc

    return [TradeOfferResponse.from_model(offer) for offer in offers]


@router.post("", response_model=TradeOfferResponse, status_code=status.HTTP_201_CREATED)
async def create_trade(
    game_id: uuid.UUID,
    data: CreateTradeOfferRequest,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TradeOfferResponse:
    try:
        offer = await trade_service.create_trade_offer(
            db,
            game_id,
            user.id,
            data.offer_type,
            data.terms,
            data.buyer_user_id,
            data.expires_in_minutes,
        )
    except Exception as exc:
        raise _map_common_errors(exc) from exc

    await connection_manager.broadcast(
        game_id,
        "trade.created",
        {
            "trade_id": str(offer.id),
            "seller_id": str(offer.seller_id),
            "buyer_id": str(offer.buyer_id) if offer.buyer_id else None,
            "offer_type": offer.offer_type.value,
        },
    )
    return TradeOfferResponse.from_model(offer)


@router.post("/{trade_id}/accept", response_model=TradeOfferResponse)
async def accept_trade(
    game_id: uuid.UUID,
    trade_id: uuid.UUID,
    data: AcceptTradeOfferRequest,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TradeOfferResponse:
    try:
        offer = await trade_service.accept_trade_offer(
            db, game_id, user.id, trade_id, data.buyer_station_id
        )
    except Exception as exc:
        raise _map_common_errors(exc) from exc

    await connection_manager.broadcast(
        game_id,
        "trade.accepted",
        {"trade_id": str(offer.id), "buyer_id": str(offer.buyer_id)},
    )
    return TradeOfferResponse.from_model(offer)


@router.post("/{trade_id}/reject", response_model=TradeOfferResponse)
async def reject_trade(
    game_id: uuid.UUID,
    trade_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TradeOfferResponse:
    try:
        offer = await trade_service.reject_trade_offer(db, game_id, user.id, trade_id)
    except Exception as exc:
        raise _map_common_errors(exc) from exc

    await connection_manager.broadcast(game_id, "trade.rejected", {"trade_id": str(offer.id)})
    return TradeOfferResponse.from_model(offer)


@router.post("/{trade_id}/cancel", response_model=TradeOfferResponse)
async def cancel_trade(
    game_id: uuid.UUID,
    trade_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TradeOfferResponse:
    try:
        offer = await trade_service.cancel_trade_offer(db, game_id, user.id, trade_id)
    except Exception as exc:
        raise _map_common_errors(exc) from exc

    await connection_manager.broadcast(game_id, "trade.cancelled", {"trade_id": str(offer.id)})
    return TradeOfferResponse.from_model(offer)


@router.post("/{trade_id}/counter", response_model=TradeOfferResponse)
async def counter_trade(
    game_id: uuid.UUID,
    trade_id: uuid.UUID,
    data: CounterTradeOfferRequest,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TradeOfferResponse:
    try:
        new_offer = await trade_service.counter_trade_offer(
            db, game_id, user.id, trade_id, data.terms, data.expires_in_minutes
        )
    except Exception as exc:
        raise _map_common_errors(exc) from exc

    await connection_manager.broadcast(game_id, "trade.rejected", {"trade_id": str(trade_id)})
    await connection_manager.broadcast(
        game_id,
        "trade.created",
        {
            "trade_id": str(new_offer.id),
            "seller_id": str(new_offer.seller_id),
            "buyer_id": str(new_offer.buyer_id) if new_offer.buyer_id else None,
            "offer_type": new_offer.offer_type.value,
        },
    )
    return TradeOfferResponse.from_model(new_offer)
