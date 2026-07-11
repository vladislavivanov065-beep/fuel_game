import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.financial_transaction import (
    TRANSACTION_TYPE_STATION_PURCHASE,
    FinancialTransaction,
)
from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom, GameStatus
from app.db.models.game_station import GameStation
from app.db.models.station_fuel import StationFuel
from app.db.models.station_template import StationTemplate
from app.db.session import async_session_factory
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.schemas.game_settings import GameSettings
from app.services.auth_service import register_user
from app.services.game_service import create_game, join_game, start_game
from app.services.station_service import (
    GameNotRunningError,
    InsufficientFundsError,
    NotAGameMemberError,
    StationAlreadyOwnedError,
    create_game_stations_for_game,
    list_game_stations,
    purchase_station,
)

# Each helper opens its own session, mirroring production usage where every
# HTTP request gets a fresh AsyncSession (avoids stale-identity-map issues
# that a single shared session would hit across sequential mutating calls).


async def _register(email: str, display_name: str = "Player") -> uuid.UUID:
    async with async_session_factory() as db:
        user, _ = await register_user(
            db,
            RegisterRequest(email=email, password="correcthorsebattery", display_name=display_name),
        )
        return user.id


async def _create_game(creator_id: uuid.UUID, name: str = "Purchase Test") -> tuple[uuid.UUID, str]:
    async with async_session_factory() as db:
        game = await create_game(db, creator_id, CreateGameRequest(name=name))
        return game.id, game.invite_code


async def _add_station_template(base_price: str = "3000000.00") -> None:
    async with async_session_factory() as db:
        db.add(
            StationTemplate(
                name="Purchase Station",
                latitude=56.0,
                longitude=47.0,
                base_price=base_price,
                metadata_json={},
            )
        )
        await db.commit()


async def _join_game(game_id: uuid.UUID, user_id: uuid.UUID, invite_code: str) -> None:
    async with async_session_factory() as db:
        await join_game(db, game_id, user_id, invite_code)


async def _start_game(game_id: uuid.UUID, creator_id: uuid.UUID) -> None:
    async with async_session_factory() as db:
        await start_game(db, game_id, creator_id)


async def _first_station_id(game_id: uuid.UUID) -> uuid.UUID:
    async with async_session_factory() as db:
        stations = await list_game_stations(db, game_id)
        return stations[0].id


async def _setup_running_game_with_station(
    creator_email: str,
    base_price: str = "3000000.00",
    other_emails: list[str] | None = None,
) -> tuple[uuid.UUID, uuid.UUID, str, list[uuid.UUID]]:
    creator_id = await _register(creator_email, "Creator")
    game_id, invite_code = await _create_game(creator_id)
    await _add_station_template(base_price)

    other_ids = []
    for email in other_emails or []:
        other_id = await _register(email, "Other")
        await _join_game(game_id, other_id, invite_code)
        other_ids.append(other_id)

    await _start_game(game_id, creator_id)
    return game_id, creator_id, invite_code, other_ids


async def test_create_game_stations_for_game_creates_station_and_fuel_rows(
    db_session: AsyncSession,
) -> None:
    creator_id = await _register("stationsvc@example.com", "Owner")
    game_id, _invite_code = await _create_game(creator_id, "Station Service Test")

    db_session.add_all(
        [
            StationTemplate(
                name="Station A",
                latitude=56.0,
                longitude=47.0,
                base_price="3000000.00",
                metadata_json={},
            ),
            StationTemplate(
                name="Station B",
                latitude=56.1,
                longitude=47.1,
                base_price="3200000.00",
                metadata_json={},
            ),
        ]
    )
    await db_session.commit()

    created = await create_game_stations_for_game(db_session, game_id, GameSettings())
    await db_session.commit()

    assert created == 2

    stations = (
        (await db_session.execute(select(GameStation).where(GameStation.game_id == game_id)))
        .scalars()
        .all()
    )
    assert len(stations) == 2
    assert all(station.owner_player_id is None for station in stations)
    assert all(station.status == "active" for station in stations)

    station_ids = [station.id for station in stations]
    fuels = (
        (
            await db_session.execute(
                select(StationFuel).where(StationFuel.game_station_id.in_(station_ids))
            )
        )
        .scalars()
        .all()
    )
    assert len(fuels) == 6
    assert all(fuel.current_liters == 0 for fuel in fuels)


async def test_purchase_station_succeeds_and_records_transaction() -> None:
    game_id, creator_id, _invite_code, _others = await _setup_running_game_with_station(
        "buyer1@example.com"
    )
    station_id = await _first_station_id(game_id)

    async with async_session_factory() as db:
        purchased = await purchase_station(db, game_id, station_id, creator_id)

        assert purchased.owner_player_id is not None
        assert purchased.owner is not None
        assert purchased.owner.user_id == creator_id

        transactions = (
            (
                await db.execute(
                    select(FinancialTransaction).where(FinancialTransaction.game_id == game_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(transactions) == 1
        assert transactions[0].amount == Decimal("-3000000.00")
        assert transactions[0].transaction_type == TRANSACTION_TYPE_STATION_PURCHASE
        assert transactions[0].balance_before == Decimal("5000000.00")
        assert transactions[0].balance_after == Decimal("2000000.00")

        player = (
            await db.execute(
                select(GamePlayer).where(
                    GamePlayer.game_id == game_id, GamePlayer.user_id == creator_id
                )
            )
        ).scalar_one()
        assert player.balance == Decimal("2000000.00")


async def test_purchase_station_fails_if_already_owned() -> None:
    game_id, creator_id, _invite_code, others = await _setup_running_game_with_station(
        "buyer2@example.com", other_emails=["buyer2b@example.com"]
    )
    station_id = await _first_station_id(game_id)

    async with async_session_factory() as db:
        await purchase_station(db, game_id, station_id, creator_id)

    async with async_session_factory() as db:
        with pytest.raises(StationAlreadyOwnedError):
            await purchase_station(db, game_id, station_id, others[0])


async def test_purchase_station_fails_with_insufficient_funds() -> None:
    game_id, creator_id, _invite_code, _others = await _setup_running_game_with_station(
        "buyer3@example.com", base_price="99999999.00"
    )
    station_id = await _first_station_id(game_id)

    async with async_session_factory() as db:
        with pytest.raises(InsufficientFundsError):
            await purchase_station(db, game_id, station_id, creator_id)


async def test_purchase_station_fails_for_non_member() -> None:
    game_id, _creator_id, _invite_code, _others = await _setup_running_game_with_station(
        "buyer4@example.com"
    )
    station_id = await _first_station_id(game_id)
    outsider_id = await _register("outsider4@example.com", "Outsider")

    async with async_session_factory() as db:
        with pytest.raises(NotAGameMemberError):
            await purchase_station(db, game_id, station_id, outsider_id)


async def test_purchase_station_fails_if_game_not_running() -> None:
    game_id, creator_id, _invite_code, _others = await _setup_running_game_with_station(
        "buyer5@example.com"
    )
    station_id = await _first_station_id(game_id)

    async with async_session_factory() as db:
        await db.execute(
            update(GameRoom).where(GameRoom.id == game_id).values(status=GameStatus.PAUSED)
        )
        await db.commit()

    async with async_session_factory() as db:
        with pytest.raises(GameNotRunningError):
            await purchase_station(db, game_id, station_id, creator_id)


async def test_concurrent_purchase_same_station_only_one_succeeds() -> None:
    game_id, creator_id, _invite_code, others = await _setup_running_game_with_station(
        "concurrent1@example.com", other_emails=["concurrent2@example.com"]
    )
    other_id = others[0]
    station_id = await _first_station_id(game_id)

    async def attempt(user_id: uuid.UUID) -> bool:
        async with async_session_factory() as session:
            try:
                await purchase_station(session, game_id, station_id, user_id)
                return True
            except StationAlreadyOwnedError:
                return False

    results = await asyncio.gather(attempt(creator_id), attempt(other_id))

    assert sorted(results) == [False, True]
