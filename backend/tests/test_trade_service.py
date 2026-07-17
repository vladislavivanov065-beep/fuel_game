import asyncio
import copy
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.financial_transaction import FinancialTransaction
from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom
from app.db.models.game_station import GameStation
from app.db.models.station_fuel import FuelType, StationFuel
from app.db.models.station_template import StationTemplate
from app.db.models.trade_offer import TradeOfferStatus, TradeOfferType
from app.db.session import async_session_factory
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.services.auth_service import register_user
from app.services.game_service import create_game, join_game, start_game
from app.services.station_service import list_game_stations, purchase_station
from app.services.trade_service import (
    CannotTradeWithSelfError,
    InsufficientFuelError,
    InsufficientFundsError,
    NotAuthorizedForTradeError,
    StationAlreadyListedError,
    StationNotOwnedByPlayerError,
    TradeOfferNotPendingError,
    TradingDisabledError,
    accept_trade_offer,
    cancel_trade_offer,
    counter_trade_offer,
    create_trade_offer,
    list_trade_offers,
    reject_trade_offer,
)


async def _register(email: str, display_name: str) -> uuid.UUID:
    async with async_session_factory() as db:
        user, _ = await register_user(
            db,
            RegisterRequest(email=email, password="correcthorsebattery", display_name=display_name),
        )
        return user.id


async def _setup_two_owned_stations(
    name: str, extra_user_ids: list[uuid.UUID] | None = None
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Returns (game_id, seller_user_id, buyer_user_id, seller_station_id, buyer_station_id)."""
    async with async_session_factory() as db:
        db.add_all(
            [
                StationTemplate(
                    name=f"{name} Station A",
                    latitude=56.0,
                    longitude=47.0,
                    base_price="2000000.00",
                    metadata_json={},
                ),
                StationTemplate(
                    name=f"{name} Station B",
                    latitude=56.1,
                    longitude=47.1,
                    base_price="2000000.00",
                    metadata_json={},
                ),
            ]
        )
        await db.commit()

    seller_id = await _register(f"{name.lower()}seller@example.com", "Seller")
    buyer_id = await _register(f"{name.lower()}buyer@example.com", "Buyer")

    async with async_session_factory() as db:
        game = await create_game(db, seller_id, CreateGameRequest(name=name))
        game_id = game.id
        invite_code = game.invite_code

    async with async_session_factory() as db:
        await join_game(db, game_id, buyer_id, invite_code)

    for extra_user_id in extra_user_ids or []:
        async with async_session_factory() as db:
            await join_game(db, game_id, extra_user_id, invite_code)

    async with async_session_factory() as db:
        await start_game(db, game_id, seller_id)

    async with async_session_factory() as db:
        stations = await list_game_stations(db, game_id)
        station_a_id, station_b_id = stations[0].id, stations[1].id

    async with async_session_factory() as db:
        await purchase_station(db, game_id, station_a_id, seller_id)
    async with async_session_factory() as db:
        await purchase_station(db, game_id, station_b_id, buyer_id)

    return game_id, seller_id, buyer_id, station_a_id, station_b_id


async def test_create_and_accept_station_sale_transfers_ownership_and_funds() -> None:
    game_id, seller_id, buyer_id, station_id, _ = await _setup_two_owned_stations("TradeStation1")

    async with async_session_factory() as db:
        offer = await create_trade_offer(
            db,
            game_id,
            seller_id,
            TradeOfferType.STATION_SALE,
            {"station_id": str(station_id), "price": "1000000.00"},
            None,
            60,
        )
    assert offer.status == TradeOfferStatus.PENDING

    async with async_session_factory() as db:
        accepted = await accept_trade_offer(db, game_id, buyer_id, offer.id, None)
    assert accepted.status == TradeOfferStatus.ACCEPTED

    async with async_session_factory() as db:
        station = (
            await db.execute(select(GameStation).where(GameStation.id == station_id))
        ).scalar_one()
        players = {
            p.user_id: p
            for p in (
                await db.execute(select(GamePlayer).where(GamePlayer.game_id == game_id))
            ).scalars()
        }
        assert station.owner_player_id == players[buyer_id].id
        assert players[buyer_id].balance == Decimal("5000000.00") - Decimal("2000000.00") - Decimal(
            "1000000.00"
        )
        assert players[seller_id].balance == Decimal("5000000.00") - Decimal(
            "2000000.00"
        ) + Decimal("1000000.00")

        transactions = (
            (
                await db.execute(
                    select(FinancialTransaction).where(
                        FinancialTransaction.reference_type == "trade_offer",
                        FinancialTransaction.reference_id == offer.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(transactions) == 2
        assert sorted(t.amount for t in transactions) == [
            Decimal("-1000000.00"),
            Decimal("1000000.00"),
        ]


async def test_cannot_create_second_pending_listing_for_same_station() -> None:
    game_id, seller_id, _buyer_id, station_id, _ = await _setup_two_owned_stations("TradeStation2")

    async with async_session_factory() as db:
        await create_trade_offer(
            db,
            game_id,
            seller_id,
            TradeOfferType.STATION_SALE,
            {"station_id": str(station_id), "price": "1000000.00"},
            None,
            60,
        )

    async with async_session_factory() as db:
        try:
            await create_trade_offer(
                db,
                game_id,
                seller_id,
                TradeOfferType.STATION_SALE,
                {"station_id": str(station_id), "price": "1200000.00"},
                None,
                60,
            )
            raise AssertionError("expected StationAlreadyListedError")
        except StationAlreadyListedError:
            pass


async def test_concurrent_accept_only_one_succeeds() -> None:
    third_id = await _register("tradestation3third@example.com", "Third")
    game_id, seller_id, buyer_id, station_id, _ = await _setup_two_owned_stations(
        "TradeStation3", extra_user_ids=[third_id]
    )

    async with async_session_factory() as db:
        offer = await create_trade_offer(
            db,
            game_id,
            seller_id,
            TradeOfferType.STATION_SALE,
            {"station_id": str(station_id), "price": "500000.00"},
            None,
            60,
        )

    async def attempt(user_id: uuid.UUID) -> bool:
        async with async_session_factory() as db:
            try:
                await accept_trade_offer(db, game_id, user_id, offer.id, None)
                return True
            except (TradeOfferNotPendingError, StationNotOwnedByPlayerError):
                # The loser can be rejected at either the early "still pending?"
                # check or the later atomic station-ownership check, depending
                # on how the two concurrent transactions actually interleave.
                return False

    results = await asyncio.gather(attempt(buyer_id), attempt(third_id))
    assert sorted(results) == [False, True]


async def test_reject_requires_targeted_buyer() -> None:
    game_id, seller_id, buyer_id, station_id, _ = await _setup_two_owned_stations("TradeStation4")

    async with async_session_factory() as db:
        offer = await create_trade_offer(
            db,
            game_id,
            seller_id,
            TradeOfferType.STATION_SALE,
            {"station_id": str(station_id), "price": "1000000.00"},
            None,
            60,
        )

    async with async_session_factory() as db:
        try:
            await reject_trade_offer(db, game_id, buyer_id, offer.id)
            raise AssertionError("expected NotAuthorizedForTradeError")
        except NotAuthorizedForTradeError:
            pass


async def test_cancel_by_seller_marks_cancelled() -> None:
    game_id, seller_id, _buyer_id, station_id, _ = await _setup_two_owned_stations("TradeStation5")

    async with async_session_factory() as db:
        offer = await create_trade_offer(
            db,
            game_id,
            seller_id,
            TradeOfferType.STATION_SALE,
            {"station_id": str(station_id), "price": "1000000.00"},
            None,
            60,
        )

    async with async_session_factory() as db:
        cancelled = await cancel_trade_offer(db, game_id, seller_id, offer.id)
    assert cancelled.status == TradeOfferStatus.CANCELLED


async def test_counter_offer_supersedes_original_with_new_terms() -> None:
    game_id, seller_id, buyer_id, station_id, _ = await _setup_two_owned_stations("TradeStation6")

    async with async_session_factory() as db:
        offer = await create_trade_offer(
            db,
            game_id,
            seller_id,
            TradeOfferType.STATION_SALE,
            {"station_id": str(station_id), "price": "1500000.00"},
            buyer_id,
            60,
        )

    async with async_session_factory() as db:
        countered = await counter_trade_offer(
            db,
            game_id,
            buyer_id,
            offer.id,
            {"station_id": str(station_id), "price": "1000000.00"},
            60,
        )

    assert countered.id != offer.id
    assert countered.terms_json["price"] == "1000000.00"
    assert countered.seller_id == offer.seller_id
    assert countered.buyer_id == offer.buyer_id

    async with async_session_factory() as db:
        offers = await list_trade_offers(db, game_id, seller_id)
    by_id = {o.id: o for o in offers}
    assert by_id[offer.id].status == TradeOfferStatus.REJECTED
    assert by_id[countered.id].status == TradeOfferStatus.PENDING


async def test_accept_fuel_sale_transfers_liters_and_funds() -> None:
    (
        game_id,
        seller_id,
        buyer_id,
        seller_station_id,
        buyer_station_id,
    ) = await _setup_two_owned_stations("TradeFuel1")

    async with async_session_factory() as db:
        seller_fuel = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == seller_station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        seller_fuel.current_liters = Decimal("5000.00")
        buyer_fuel = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == buyer_station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        buyer_fuel.current_liters = Decimal("0.00")
        buyer_fuel.average_purchase_price = Decimal("0.00")
        await db.commit()

    async with async_session_factory() as db:
        offer = await create_trade_offer(
            db,
            game_id,
            seller_id,
            TradeOfferType.FUEL_SALE,
            {
                "station_id": str(seller_station_id),
                "fuel_type": "ai92",
                "liters": "1000.00",
                "price_per_liter": "40.00",
            },
            None,
            60,
        )

    async with async_session_factory() as db:
        accepted = await accept_trade_offer(db, game_id, buyer_id, offer.id, buyer_station_id)
    assert accepted.status == TradeOfferStatus.ACCEPTED

    async with async_session_factory() as db:
        seller_fuel = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == seller_station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        buyer_fuel = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == buyer_station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        assert seller_fuel.current_liters == Decimal("4000.00")
        assert buyer_fuel.current_liters == Decimal("1000.00")
        assert buyer_fuel.average_purchase_price == Decimal("40.00")

        players = {
            p.user_id: p
            for p in (
                await db.execute(select(GamePlayer).where(GamePlayer.game_id == game_id))
            ).scalars()
        }
        starting_after_stations = Decimal("5000000.00") - Decimal("2000000.00")
        assert players[buyer_id].balance == starting_after_stations - Decimal("40000.00")
        assert players[seller_id].balance == starting_after_stations + Decimal("40000.00")


async def test_accept_fuel_sale_fails_when_insufficient_stock() -> None:
    (
        game_id,
        seller_id,
        buyer_id,
        seller_station_id,
        buyer_station_id,
    ) = await _setup_two_owned_stations("TradeFuel2")

    async with async_session_factory() as db:
        seller_fuel = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == seller_station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        seller_fuel.current_liters = Decimal("500.00")
        await db.commit()

    async with async_session_factory() as db:
        offer = await create_trade_offer(
            db,
            game_id,
            seller_id,
            TradeOfferType.FUEL_SALE,
            {
                "station_id": str(seller_station_id),
                "fuel_type": "ai92",
                "liters": "400.00",
                "price_per_liter": "40.00",
            },
            None,
            60,
        )

    async with async_session_factory() as db:
        seller_fuel = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == seller_station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        seller_fuel.current_liters = Decimal("100.00")
        await db.commit()

    async with async_session_factory() as db:
        try:
            await accept_trade_offer(db, game_id, buyer_id, offer.id, buyer_station_id)
            raise AssertionError("expected InsufficientFuelError")
        except InsufficientFuelError:
            pass


async def test_accept_station_sale_fails_when_buyer_cannot_afford() -> None:
    game_id, seller_id, buyer_id, station_id, _ = await _setup_two_owned_stations("TradeStation7")

    async with async_session_factory() as db:
        offer = await create_trade_offer(
            db,
            game_id,
            seller_id,
            TradeOfferType.STATION_SALE,
            {"station_id": str(station_id), "price": "50000000.00"},
            None,
            60,
        )

    async with async_session_factory() as db:
        try:
            await accept_trade_offer(db, game_id, buyer_id, offer.id, None)
            raise AssertionError("expected InsufficientFundsError")
        except InsufficientFundsError:
            pass


async def test_cannot_create_offer_targeting_self() -> None:
    game_id, seller_id, _buyer_id, station_id, _ = await _setup_two_owned_stations("TradeStation8")

    async with async_session_factory() as db:
        try:
            await create_trade_offer(
                db,
                game_id,
                seller_id,
                TradeOfferType.STATION_SALE,
                {"station_id": str(station_id), "price": "1000000.00"},
                seller_id,
                60,
            )
            raise AssertionError("expected CannotTradeWithSelfError")
        except CannotTradeWithSelfError:
            pass


async def test_trading_disabled_blocks_offer_creation(db_session: AsyncSession) -> None:
    game_id, seller_id, _buyer_id, station_id, _ = await _setup_two_owned_stations("TradeStation9")

    async with async_session_factory() as db:
        game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one()
        settings_json = copy.deepcopy(game.settings_json)
        settings_json["trading_enabled"] = False
        game.settings_json = settings_json
        await db.commit()

    async with async_session_factory() as db:
        try:
            await create_trade_offer(
                db,
                game_id,
                seller_id,
                TradeOfferType.STATION_SALE,
                {"station_id": str(station_id), "price": "1000000.00"},
                None,
                60,
            )
            raise AssertionError("expected TradingDisabledError")
        except TradingDisabledError:
            pass
