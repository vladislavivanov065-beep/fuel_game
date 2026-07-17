import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update

from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom, GameStatus
from app.db.models.station_fuel import FuelType, StationFuel
from app.db.models.station_template import StationTemplate
from app.db.models.station_upgrade import UpgradeType
from app.db.models.trade_offer import TradeOfferType
from app.db.session import async_session_factory
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.schemas.game_settings import GameSettings
from app.services.auth_service import register_user
from app.services.game_service import create_game, start_game
from app.services.station_service import GameNotRunningError as StationGameNotRunningError
from app.services.station_service import (
    list_game_stations,
    purchase_station,
    set_station_fuel_price,
)
from app.services.station_upgrade_service import purchase_upgrade
from app.services.trade_service import GameNotRunningError as TradeGameNotRunningError
from app.services.trade_service import create_trade_offer
from app.simulation.game_lifecycle import compute_net_worth, maybe_finish_game


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


async def test_compute_net_worth_includes_cash_station_and_fuel() -> None:
    game_id, station_id, owner_id = await _setup_owned_station("NetWorth1")

    async with async_session_factory() as db:
        station_fuel = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        station_fuel.current_liters = Decimal("1000.00")
        station_fuel.average_purchase_price = Decimal("40.00")
        await db.commit()

    async with async_session_factory() as db:
        player = (
            await db.execute(select(GamePlayer).where(GamePlayer.game_id == game_id))
        ).scalar_one()
        net_worth = await compute_net_worth(db, game_id)

    # cash (5,000,000 - 2,000,000 station purchase) + station purchase_price (2,000,000)
    # + fuel value (1000 * 40 = 40,000) for the AI92 tank; other two tanks default to 0 liters.
    expected = player.balance + Decimal("2000000.00") + Decimal("40000.00")
    assert net_worth[player.id] == expected


async def test_compute_net_worth_includes_upgrade_invested_value() -> None:
    game_id, station_id, owner_id = await _setup_owned_station("NetWorth2")

    async with async_session_factory() as db:
        await purchase_upgrade(db, game_id, owner_id, station_id, UpgradeType.PUMPS)

    async with async_session_factory() as db:
        player = (
            await db.execute(select(GamePlayer).where(GamePlayer.game_id == game_id))
        ).scalar_one()
        game = await db.get(GameRoom, game_id)
        assert game is not None
        net_worth = await compute_net_worth(db, game_id)

    settings = GameSettings.model_validate(game.settings_json)
    pumps_cost = settings.station_upgrades["pumps"].base_cost

    async with async_session_factory() as db:
        station_fuels_value = Decimal("0")
        fuels = (
            (await db.execute(select(StationFuel).where(StationFuel.game_station_id == station_id)))
            .scalars()
            .all()
        )
        for fuel in fuels:
            station_fuels_value += fuel.current_liters * fuel.average_purchase_price

    expected = player.balance + Decimal("2000000.00") + station_fuels_value + pumps_cost
    assert net_worth[player.id] == expected


async def test_maybe_finish_game_transitions_status_and_persists_net_worth() -> None:
    game_id, station_id, owner_id = await _setup_owned_station("NetWorth3")

    async with async_session_factory() as db:
        await db.execute(
            update(GameRoom)
            .where(GameRoom.id == game_id)
            .values(started_at=datetime.now(UTC) - timedelta(hours=2))
        )
        await db.commit()

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        assert game is not None
        net_worth = await maybe_finish_game(db, game)

    assert net_worth is not None

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        assert game is not None
        assert game.status == GameStatus.FINISHED
        assert game.finished_at is not None

        player = (
            await db.execute(select(GamePlayer).where(GamePlayer.game_id == game_id))
        ).scalar_one()
        assert player.net_worth == net_worth[player.id]
        assert player.net_worth > Decimal("0")


async def test_maybe_finish_game_is_noop_before_duration_elapsed() -> None:
    game_id, _station_id, _owner_id = await _setup_owned_station("NetWorth4")

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        assert game is not None
        result = await maybe_finish_game(db, game)

    assert result is None

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        assert game is not None
        assert game.status == GameStatus.RUNNING


async def test_maybe_finish_game_is_idempotent_when_already_finished() -> None:
    game_id, _station_id, _owner_id = await _setup_owned_station("NetWorth5")

    async with async_session_factory() as db:
        await db.execute(
            update(GameRoom)
            .where(GameRoom.id == game_id)
            .values(started_at=datetime.now(UTC) - timedelta(hours=2))
        )
        await db.commit()

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        assert game is not None
        first = await maybe_finish_game(db, game)
    assert first is not None

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        assert game is not None
        second = await maybe_finish_game(db, game)
    assert second is None


async def test_actions_are_blocked_once_game_is_finished() -> None:
    game_id, station_id, owner_id = await _setup_owned_station("NetWorth6")

    async with async_session_factory() as db:
        await db.execute(
            update(GameRoom)
            .where(GameRoom.id == game_id)
            .values(started_at=datetime.now(UTC) - timedelta(hours=2))
        )
        await db.commit()

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        assert game is not None
        assert await maybe_finish_game(db, game) is not None

    async with async_session_factory() as db:
        try:
            await set_station_fuel_price(
                db, game_id, station_id, owner_id, FuelType.AI92, Decimal("50.00")
            )
            raise AssertionError("expected GameNotRunningError")
        except StationGameNotRunningError:
            pass

    async with async_session_factory() as db:
        try:
            await create_trade_offer(
                db,
                game_id,
                owner_id,
                TradeOfferType.STATION_SALE,
                {"station_id": str(station_id), "price": "1000000.00"},
                None,
                60,
            )
            raise AssertionError("expected GameNotRunningError")
        except TradeGameNotRunningError:
            pass
