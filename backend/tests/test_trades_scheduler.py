import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom
from app.db.models.station_template import StationTemplate
from app.db.models.trade_offer import TradeOffer, TradeOfferStatus, TradeOfferType
from app.db.session import async_session_factory
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.services.auth_service import register_user
from app.services.game_service import create_game, start_game
from app.services.station_service import list_game_stations, purchase_station
from app.simulation.trades import expire_due_trade_offers_for_game


async def _register(email: str) -> uuid.UUID:
    async with async_session_factory() as db:
        user, _ = await register_user(
            db, RegisterRequest(email=email, password="correcthorsebattery", display_name="Owner")
        )
        return user.id


async def _setup_owned_station(name: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with async_session_factory() as db:
        db.add(
            StationTemplate(
                name=f"{name} Station",
                latitude=56.0,
                longitude=47.0,
                base_price="2000000.00",
                metadata_json={},
            )
        )
        await db.commit()

    owner_id = await _register(f"{name.lower()}@example.com")
    async with async_session_factory() as db:
        game = await create_game(db, owner_id, CreateGameRequest(name=name))
        game_id = game.id
    async with async_session_factory() as db:
        await start_game(db, game_id, owner_id)
    async with async_session_factory() as db:
        stations = await list_game_stations(db, game_id)
        station_id = stations[0].id
    async with async_session_factory() as db:
        await purchase_station(db, game_id, station_id, owner_id)

    return game_id, station_id, owner_id


async def test_expire_due_trade_offers_flips_pending_to_expired() -> None:
    game_id, station_id, owner_id = await _setup_owned_station("TradeExpire1")

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        assert game is not None
        player = (
            await db.execute(select(GamePlayer).where(GamePlayer.game_id == game_id))
        ).scalar_one()

        offer = TradeOffer(
            game_id=game_id,
            seller_id=player.id,
            buyer_id=None,
            offer_type=TradeOfferType.STATION_SALE,
            status=TradeOfferStatus.PENDING,
            terms_json={"station_id": str(station_id), "price": "1000000.00"},
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        db.add(offer)
        await db.commit()
        offer_id = offer.id

    async with async_session_factory() as db:
        expired_ids = await expire_due_trade_offers_for_game(db, game_id)

    assert offer_id in expired_ids

    async with async_session_factory() as db:
        offer = await db.get(TradeOffer, offer_id)
        assert offer is not None
        assert offer.status == TradeOfferStatus.EXPIRED


async def test_expire_due_trade_offers_ignores_still_pending() -> None:
    game_id, station_id, owner_id = await _setup_owned_station("TradeExpire2")

    async with async_session_factory() as db:
        player = (
            await db.execute(select(GamePlayer).where(GamePlayer.game_id == game_id))
        ).scalar_one()

        offer = TradeOffer(
            game_id=game_id,
            seller_id=player.id,
            buyer_id=None,
            offer_type=TradeOfferType.STATION_SALE,
            status=TradeOfferStatus.PENDING,
            terms_json={"station_id": str(station_id), "price": "1000000.00"},
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        db.add(offer)
        await db.commit()
        offer_id = offer.id

    async with async_session_factory() as db:
        expired_ids = await expire_due_trade_offers_for_game(db, game_id)

    assert offer_id not in expired_ids

    async with async_session_factory() as db:
        offer = await db.get(TradeOffer, offer_id)
        assert offer is not None
        assert offer.status == TradeOfferStatus.PENDING
