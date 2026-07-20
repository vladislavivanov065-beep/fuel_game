import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import CursorResult, and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.financial_transaction import (
    TRANSACTION_TYPE_TRADE_FUEL_SALE,
    TRANSACTION_TYPE_TRADE_STATION_SALE,
    FinancialTransaction,
)
from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom, GameStatus
from app.db.models.game_station import GameStation
from app.db.models.station_fuel import StationFuel
from app.db.models.trade_offer import TradeOffer, TradeOfferStatus, TradeOfferType
from app.schemas.game_settings import GameSettings
from app.schemas.trade import FuelSaleTerms, StationSaleTerms


class GameNotFoundError(Exception):
    pass


class GameNotRunningError(Exception):
    pass


class NotAGameMemberError(Exception):
    pass


class TradingDisabledError(Exception):
    pass


class StationNotFoundError(Exception):
    pass


class StationNotOwnedByPlayerError(Exception):
    pass


class StationAlreadyListedError(Exception):
    pass


class FuelTypeNotFoundError(Exception):
    pass


class InsufficientFuelError(Exception):
    pass


class InsufficientCapacityError(Exception):
    pass


class InsufficientFundsError(Exception):
    pass


class CannotTradeWithSelfError(Exception):
    pass


class BuyerStationRequiredError(Exception):
    pass


class TradeOfferNotFoundError(Exception):
    pass


class TradeOfferNotPendingError(Exception):
    pass


class TradeOfferNotTargetedError(Exception):
    pass


class NotAuthorizedForTradeError(Exception):
    pass


class InvalidCounterTermsError(Exception):
    pass


async def _get_running_game(db: AsyncSession, game_id: uuid.UUID) -> GameRoom:
    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError
    if game.status != GameStatus.RUNNING:
        raise GameNotRunningError
    return game


async def _get_member_player(
    db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID
) -> GamePlayer:
    player = (
        await db.execute(
            select(GamePlayer).where(GamePlayer.game_id == game_id, GamePlayer.user_id == user_id)
        )
    ).scalar_one_or_none()
    if player is None:
        raise NotAGameMemberError
    return player


def _require_trading_enabled(game: GameRoom) -> None:
    settings = GameSettings.model_validate(game.settings_json)
    if not settings.trading_enabled:
        raise TradingDisabledError


async def _get_offer(db: AsyncSession, game_id: uuid.UUID, trade_id: uuid.UUID) -> TradeOffer:
    offer = (
        await db.execute(
            select(TradeOffer).where(TradeOffer.id == trade_id, TradeOffer.game_id == game_id)
        )
    ).scalar_one_or_none()
    if offer is None:
        raise TradeOfferNotFoundError
    return offer


def _record_trade_payment(
    db: AsyncSession,
    game_id: uuid.UUID,
    trade_id: uuid.UUID,
    transaction_type: str,
    buyer: GamePlayer,
    seller: GamePlayer,
    amount: Decimal,
) -> None:
    buyer_before = buyer.balance
    buyer.balance = buyer.balance - amount
    db.add(
        FinancialTransaction(
            game_id=game_id,
            player_id=buyer.id,
            transaction_type=transaction_type,
            amount=-amount,
            balance_before=buyer_before,
            balance_after=buyer.balance,
            reference_type="trade_offer",
            reference_id=trade_id,
        )
    )
    seller_before = seller.balance
    seller.balance = seller.balance + amount
    db.add(
        FinancialTransaction(
            game_id=game_id,
            player_id=seller.id,
            transaction_type=transaction_type,
            amount=amount,
            balance_before=seller_before,
            balance_after=seller.balance,
            reference_type="trade_offer",
            reference_id=trade_id,
        )
    )


async def list_trade_offers(
    db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID
) -> list[TradeOffer]:
    player = await _get_member_player(db, game_id, user_id)
    stmt = (
        select(TradeOffer)
        .where(
            TradeOffer.game_id == game_id,
            or_(
                TradeOffer.seller_id == player.id,
                TradeOffer.buyer_id == player.id,
                and_(TradeOffer.buyer_id.is_(None), TradeOffer.status == TradeOfferStatus.PENDING),
            ),
        )
        .order_by(TradeOffer.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars())


async def create_trade_offer(
    db: AsyncSession,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
    offer_type: TradeOfferType,
    terms: dict[str, object],
    buyer_user_id: uuid.UUID | None,
    expires_in_minutes: int,
) -> TradeOffer:
    game = await _get_running_game(db, game_id)
    _require_trading_enabled(game)
    player = await _get_member_player(db, game_id, user_id)

    buyer_player_id: uuid.UUID | None = None
    if buyer_user_id is not None:
        buyer_player = await _get_member_player(db, game_id, buyer_user_id)
        if buyer_player.id == player.id:
            raise CannotTradeWithSelfError
        buyer_player_id = buyer_player.id

    if offer_type == TradeOfferType.STATION_SALE:
        station_terms = StationSaleTerms.model_validate(terms)
        station = (
            await db.execute(
                select(GameStation).where(
                    GameStation.id == station_terms.station_id, GameStation.game_id == game_id
                )
            )
        ).scalar_one_or_none()
        if station is None:
            raise StationNotFoundError
        if station.owner_player_id != player.id:
            raise StationNotOwnedByPlayerError

        existing_listings = (
            (
                await db.execute(
                    select(TradeOffer).where(
                        TradeOffer.game_id == game_id,
                        TradeOffer.offer_type == TradeOfferType.STATION_SALE,
                        TradeOffer.status == TradeOfferStatus.PENDING,
                    )
                )
            )
            .scalars()
            .all()
        )
        if any(
            row.terms_json.get("station_id") == str(station_terms.station_id)
            for row in existing_listings
        ):
            raise StationAlreadyListedError

        terms_json = station_terms.model_dump(mode="json")
    else:
        fuel_terms = FuelSaleTerms.model_validate(terms)
        station = (
            await db.execute(
                select(GameStation).where(
                    GameStation.id == fuel_terms.station_id, GameStation.game_id == game_id
                )
            )
        ).scalar_one_or_none()
        if station is None:
            raise StationNotFoundError
        if station.owner_player_id != player.id:
            raise StationNotOwnedByPlayerError

        station_fuel = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == fuel_terms.station_id,
                    StationFuel.fuel_type == fuel_terms.fuel_type,
                )
            )
        ).scalar_one_or_none()
        if station_fuel is None:
            raise FuelTypeNotFoundError
        if station_fuel.current_liters < fuel_terms.liters:
            raise InsufficientFuelError

        terms_json = fuel_terms.model_dump(mode="json")

    offer = TradeOffer(
        game_id=game_id,
        seller_id=player.id,
        buyer_id=buyer_player_id,
        offer_type=offer_type,
        terms_json=terms_json,
        expires_at=datetime.now(UTC) + timedelta(minutes=expires_in_minutes),
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)
    return offer


async def accept_trade_offer(
    db: AsyncSession,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
    trade_id: uuid.UUID,
    buyer_station_id: uuid.UUID | None,
) -> TradeOffer:
    game = await _get_running_game(db, game_id)
    _require_trading_enabled(game)
    acting_player = await _get_member_player(db, game_id, user_id)

    offer = await _get_offer(db, game_id, trade_id)
    if offer.status != TradeOfferStatus.PENDING:
        raise TradeOfferNotPendingError
    if offer.seller_id == acting_player.id:
        raise CannotTradeWithSelfError
    if offer.buyer_id is not None and offer.buyer_id != acting_player.id:
        raise NotAuthorizedForTradeError

    ordered_ids = sorted([acting_player.id, offer.seller_id], key=str)
    locked_rows = (
        (
            await db.execute(
                select(GamePlayer).where(GamePlayer.id.in_(ordered_ids)).with_for_update()
            )
        )
        .scalars()
        .all()
    )
    players_by_id = {row.id: row for row in locked_rows}
    buyer = players_by_id[acting_player.id]
    seller = players_by_id[offer.seller_id]

    if offer.offer_type == TradeOfferType.STATION_SALE:
        station_terms = StationSaleTerms.model_validate(offer.terms_json)
        if buyer.balance < station_terms.price:
            raise InsufficientFundsError

        claim_result = cast(
            CursorResult[Any],
            await db.execute(
                update(GameStation)
                .where(
                    GameStation.id == station_terms.station_id,
                    GameStation.owner_player_id == seller.id,
                )
                .values(owner_player_id=buyer.id)
            ),
        )
        if claim_result.rowcount != 1:
            await db.rollback()
            raise StationNotOwnedByPlayerError

        offer_result = cast(
            CursorResult[Any],
            await db.execute(
                update(TradeOffer)
                .where(TradeOffer.id == trade_id, TradeOffer.status == TradeOfferStatus.PENDING)
                .values(status=TradeOfferStatus.ACCEPTED, buyer_id=buyer.id)
            ),
        )
        if offer_result.rowcount != 1:
            await db.rollback()
            raise TradeOfferNotPendingError

        _record_trade_payment(
            db,
            game_id,
            trade_id,
            TRANSACTION_TYPE_TRADE_STATION_SALE,
            buyer,
            seller,
            station_terms.price,
        )
    else:
        fuel_terms = FuelSaleTerms.model_validate(offer.terms_json)
        if buyer_station_id is None:
            raise BuyerStationRequiredError

        buyer_station = (
            await db.execute(
                select(GameStation).where(
                    GameStation.id == buyer_station_id, GameStation.game_id == game_id
                )
            )
        ).scalar_one_or_none()
        if buyer_station is None:
            raise StationNotFoundError
        if buyer_station.owner_player_id != buyer.id:
            raise StationNotOwnedByPlayerError

        buyer_fuel = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == buyer_station_id,
                    StationFuel.fuel_type == fuel_terms.fuel_type,
                )
            )
        ).scalar_one_or_none()
        if buyer_fuel is None:
            raise FuelTypeNotFoundError

        total_price = fuel_terms.price_per_liter * fuel_terms.liters
        if buyer.balance < total_price:
            raise InsufficientFundsError
        if buyer_fuel.current_liters + fuel_terms.liters > buyer_fuel.capacity_liters:
            raise InsufficientCapacityError

        decrement_result = cast(
            CursorResult[Any],
            await db.execute(
                update(StationFuel)
                .where(
                    StationFuel.game_station_id == fuel_terms.station_id,
                    StationFuel.fuel_type == fuel_terms.fuel_type,
                    StationFuel.current_liters >= fuel_terms.liters,
                )
                .values(current_liters=StationFuel.current_liters - fuel_terms.liters)
            ),
        )
        if decrement_result.rowcount != 1:
            await db.rollback()
            raise InsufficientFuelError

        offer_result = cast(
            CursorResult[Any],
            await db.execute(
                update(TradeOffer)
                .where(TradeOffer.id == trade_id, TradeOffer.status == TradeOfferStatus.PENDING)
                .values(status=TradeOfferStatus.ACCEPTED, buyer_id=buyer.id)
            ),
        )
        if offer_result.rowcount != 1:
            await db.rollback()
            raise TradeOfferNotPendingError

        new_total_liters = buyer_fuel.current_liters + fuel_terms.liters
        if new_total_liters > 0:
            buyer_fuel.average_purchase_price = (
                buyer_fuel.average_purchase_price * buyer_fuel.current_liters
                + fuel_terms.price_per_liter * fuel_terms.liters
            ) / new_total_liters
        buyer_fuel.current_liters = new_total_liters

        _record_trade_payment(
            db, game_id, trade_id, TRANSACTION_TYPE_TRADE_FUEL_SALE, buyer, seller, total_price
        )

    await db.commit()
    await db.refresh(offer)
    return offer


async def reject_trade_offer(
    db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID, trade_id: uuid.UUID
) -> TradeOffer:
    await _get_running_game(db, game_id)
    player = await _get_member_player(db, game_id, user_id)
    offer = await _get_offer(db, game_id, trade_id)

    if offer.buyer_id != player.id:
        raise NotAuthorizedForTradeError

    result = cast(
        CursorResult[Any],
        await db.execute(
            update(TradeOffer)
            .where(TradeOffer.id == trade_id, TradeOffer.status == TradeOfferStatus.PENDING)
            .values(status=TradeOfferStatus.REJECTED)
        ),
    )
    if result.rowcount != 1:
        await db.rollback()
        raise TradeOfferNotPendingError

    await db.commit()
    await db.refresh(offer)
    return offer


async def cancel_trade_offer(
    db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID, trade_id: uuid.UUID
) -> TradeOffer:
    await _get_running_game(db, game_id)
    player = await _get_member_player(db, game_id, user_id)
    offer = await _get_offer(db, game_id, trade_id)

    if offer.seller_id != player.id:
        raise NotAuthorizedForTradeError

    result = cast(
        CursorResult[Any],
        await db.execute(
            update(TradeOffer)
            .where(TradeOffer.id == trade_id, TradeOffer.status == TradeOfferStatus.PENDING)
            .values(status=TradeOfferStatus.CANCELLED)
        ),
    )
    if result.rowcount != 1:
        await db.rollback()
        raise TradeOfferNotPendingError

    await db.commit()
    await db.refresh(offer)
    return offer


async def counter_trade_offer(
    db: AsyncSession,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
    trade_id: uuid.UUID,
    new_terms: dict[str, object],
    expires_in_minutes: int,
) -> TradeOffer:
    game = await _get_running_game(db, game_id)
    _require_trading_enabled(game)
    player = await _get_member_player(db, game_id, user_id)
    offer = await _get_offer(db, game_id, trade_id)

    if offer.status != TradeOfferStatus.PENDING:
        raise TradeOfferNotPendingError
    if offer.buyer_id is None:
        raise TradeOfferNotTargetedError
    if player.id not in (offer.seller_id, offer.buyer_id):
        raise NotAuthorizedForTradeError

    if offer.offer_type == TradeOfferType.STATION_SALE:
        parsed = StationSaleTerms.model_validate(new_terms)
        original = StationSaleTerms.model_validate(offer.terms_json)
        if parsed.station_id != original.station_id:
            raise InvalidCounterTermsError
        new_terms_json = parsed.model_dump(mode="json")
    else:
        parsed_fuel = FuelSaleTerms.model_validate(new_terms)
        original_fuel = FuelSaleTerms.model_validate(offer.terms_json)
        if (
            parsed_fuel.station_id != original_fuel.station_id
            or parsed_fuel.fuel_type != original_fuel.fuel_type
        ):
            raise InvalidCounterTermsError
        new_terms_json = parsed_fuel.model_dump(mode="json")

    supersede_result = cast(
        CursorResult[Any],
        await db.execute(
            update(TradeOffer)
            .where(TradeOffer.id == trade_id, TradeOffer.status == TradeOfferStatus.PENDING)
            .values(status=TradeOfferStatus.REJECTED)
        ),
    )
    if supersede_result.rowcount != 1:
        await db.rollback()
        raise TradeOfferNotPendingError

    new_offer = TradeOffer(
        game_id=game_id,
        seller_id=offer.seller_id,
        buyer_id=offer.buyer_id,
        offer_type=offer.offer_type,
        terms_json=new_terms_json,
        expires_at=datetime.now(UTC) + timedelta(minutes=expires_in_minutes),
    )
    db.add(new_offer)
    await db.commit()
    await db.refresh(new_offer)
    return new_offer
