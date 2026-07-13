import copy
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.financial_transaction import FinancialTransaction
from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom
from app.db.models.station_template import StationTemplate
from app.db.models.station_upgrade import UpgradeStatus, UpgradeType
from app.db.session import async_session_factory
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.services.auth_service import register_user
from app.services.game_service import create_game, join_game, start_game
from app.services.station_service import list_game_stations, purchase_station
from app.services.station_upgrade_service import (
    GameNotRunningError,
    InsufficientFundsError,
    NotAGameMemberError,
    StationLevelTooLowError,
    StationNotOwnedByPlayerError,
    list_station_upgrades,
    next_upgrade_cost,
    purchase_upgrade,
)


async def _register(email: str) -> uuid.UUID:
    async with async_session_factory() as db:
        user, _ = await register_user(
            db, RegisterRequest(email=email, password="correcthorsebattery", display_name="Owner")
        )
        return user.id


async def _setup_owned_station(name: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Returns (game_id, station_id, owner_user_id)."""
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

    creator_id = await _register(f"{name.lower()}@example.com")
    async with async_session_factory() as db:
        game = await create_game(db, creator_id, CreateGameRequest(name=name))
        game_id = game.id
    async with async_session_factory() as db:
        await start_game(db, game_id, creator_id)
    async with async_session_factory() as db:
        stations = await list_game_stations(db, game_id)
        station_id = stations[0].id
    async with async_session_factory() as db:
        await purchase_station(db, game_id, station_id, creator_id)

    return game_id, station_id, creator_id


async def test_purchase_upgrade_creates_level_one_under_construction(
    db_session: AsyncSession,
) -> None:
    game_id, station_id, owner_id = await _setup_owned_station("UpgradeFirst")

    async with async_session_factory() as db:
        upgrade = await purchase_upgrade(db, game_id, owner_id, station_id, UpgradeType.PUMPS)

    assert upgrade.level == 1
    assert upgrade.status == UpgradeStatus.UNDER_CONSTRUCTION
    assert upgrade.completed_at > upgrade.started_at

    async with async_session_factory() as db:
        transactions = (
            (
                await db.execute(
                    select(FinancialTransaction).where(
                        FinancialTransaction.reference_type == "station_upgrade"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(transactions) == 1
        assert transactions[0].amount < Decimal("0")

        player = (
            await db.execute(select(GamePlayer).where(GamePlayer.game_id == game_id))
        ).scalar_one()
        assert player.balance == transactions[0].balance_after


async def test_purchase_upgrade_again_increments_level_and_cost(db_session: AsyncSession) -> None:
    game_id, station_id, owner_id = await _setup_owned_station("UpgradeLevelUp")

    async with async_session_factory() as db:
        first = await purchase_upgrade(db, game_id, owner_id, station_id, UpgradeType.SHOP)
    assert first.level == 1

    async with async_session_factory() as db:
        second = await purchase_upgrade(db, game_id, owner_id, station_id, UpgradeType.SHOP)
    assert second.level == 2
    assert second.id == first.id
    assert second.status == UpgradeStatus.UNDER_CONSTRUCTION

    async with async_session_factory() as db:
        upgrades = await list_station_upgrades(db, game_id, station_id)
    matching = [u for u in upgrades if u.upgrade_type == UpgradeType.SHOP]
    assert len(matching) == 1
    assert matching[0].level == 2


async def test_purchase_upgrade_fails_with_insufficient_funds(db_session: AsyncSession) -> None:
    game_id, station_id, owner_id = await _setup_owned_station("UpgradePoor")

    async with async_session_factory() as db:
        player = (
            await db.execute(select(GamePlayer).where(GamePlayer.game_id == game_id))
        ).scalar_one()
        player.balance = Decimal("1.00")
        await db.commit()

    async with async_session_factory() as db:
        try:
            await purchase_upgrade(db, game_id, owner_id, station_id, UpgradeType.FOOD_COURT)
            raise AssertionError("expected InsufficientFundsError")
        except InsufficientFundsError:
            pass


async def test_purchase_upgrade_fails_for_non_owner(db_session: AsyncSession) -> None:
    async with async_session_factory() as db:
        db.add(
            StationTemplate(
                name="UpgradeNotOwner Station",
                latitude=56.0,
                longitude=47.0,
                base_price="2000000.00",
                metadata_json={},
            )
        )
        await db.commit()

    owner_id = await _register("upgradenotowner_owner@example.com")
    other_id = await _register("upgradenotowner_other@example.com")

    async with async_session_factory() as db:
        game = await create_game(db, owner_id, CreateGameRequest(name="UpgradeNotOwner"))
        game_id = game.id
        invite_code = game.invite_code

    async with async_session_factory() as db:
        await join_game(db, game_id, other_id, invite_code)
    async with async_session_factory() as db:
        await start_game(db, game_id, owner_id)
    async with async_session_factory() as db:
        stations = await list_game_stations(db, game_id)
        station_id = stations[0].id
    async with async_session_factory() as db:
        await purchase_station(db, game_id, station_id, owner_id)

    async with async_session_factory() as db:
        try:
            await purchase_upgrade(db, game_id, other_id, station_id, UpgradeType.PARKING)
            raise AssertionError("expected StationNotOwnedByPlayerError")
        except StationNotOwnedByPlayerError:
            pass


async def test_purchase_upgrade_requires_membership(db_session: AsyncSession) -> None:
    game_id, station_id, _owner_id = await _setup_owned_station("UpgradeNoMember")

    async with async_session_factory() as db:
        try:
            await purchase_upgrade(db, game_id, uuid.uuid4(), station_id, UpgradeType.PARKING)
            raise AssertionError("expected NotAGameMemberError")
        except NotAGameMemberError:
            pass


async def test_purchase_upgrade_requires_station_level(db_session: AsyncSession) -> None:
    game_id, station_id, owner_id = await _setup_owned_station("UpgradeLowLevel")

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        settings_json = copy.deepcopy(game.settings_json)
        settings_json["station_upgrades"]["parking"]["min_station_level"] = 5
        game.settings_json = settings_json
        await db.commit()

    async with async_session_factory() as db:
        try:
            await purchase_upgrade(db, game_id, owner_id, station_id, UpgradeType.PARKING)
            raise AssertionError("expected StationLevelTooLowError")
        except StationLevelTooLowError:
            pass


async def test_purchase_upgrade_requires_running_game(db_session: AsyncSession) -> None:
    async with async_session_factory() as db:
        db.add(
            StationTemplate(
                name="NotRunning Station",
                latitude=56.0,
                longitude=47.0,
                base_price="2000000.00",
                metadata_json={},
            )
        )
        await db.commit()

    creator_id = await _register("upgradenotrunning@example.com")
    async with async_session_factory() as db:
        game = await create_game(db, creator_id, CreateGameRequest(name="NotRunning"))
        game_id = game.id

    async with async_session_factory() as db:
        try:
            await purchase_upgrade(db, game_id, creator_id, uuid.uuid4(), UpgradeType.PARKING)
            raise AssertionError("expected GameNotRunningError")
        except GameNotRunningError:
            pass


def test_next_upgrade_cost_scales_linearly_with_level() -> None:
    from app.schemas.game_settings import StationUpgradeTypeSettings

    settings = StationUpgradeTypeSettings(
        base_cost=Decimal("100000"),
        cost_per_level=Decimal("50000"),
        build_minutes=10.0,
        maintenance_per_level=Decimal("0"),
        bonus_per_level=1.0,
        revenue_per_level=Decimal("0"),
    )
    assert next_upgrade_cost(settings, 0) == Decimal("100000")
    assert next_upgrade_cost(settings, 1) == Decimal("150000")
    assert next_upgrade_cost(settings, 2) == Decimal("200000")
