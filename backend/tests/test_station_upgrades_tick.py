import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.game_station import GameStation
from app.db.models.station_fuel import FuelType, StationFuel
from app.db.models.station_template import StationTemplate
from app.db.models.station_upgrade import StationUpgrade, UpgradeStatus, UpgradeType
from app.db.session import async_session_factory
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.services.auth_service import register_user
from app.services.game_service import create_game, start_game
from app.services.station_service import list_game_stations, purchase_station
from app.services.station_upgrade_service import purchase_upgrade
from app.simulation.station_upgrades import complete_due_upgrades_for_game, effective_upgrade_level


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


async def test_tick_activates_due_upgrade_and_applies_tanks_capacity(
    db_session: AsyncSession,
) -> None:
    game_id, station_id, owner_id = await _setup_owned_station("TickTanks")

    async with async_session_factory() as db:
        before_fuel = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        before_capacity = before_fuel.capacity_liters

    async with async_session_factory() as db:
        upgrade = await purchase_upgrade(db, game_id, owner_id, station_id, UpgradeType.TANKS)
        upgrade_id = upgrade.id

    async with async_session_factory() as db:
        upgrade = await db.get(StationUpgrade, upgrade_id)
        assert upgrade is not None
        upgrade.completed_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

    async with async_session_factory() as db:
        result = await complete_due_upgrades_for_game(db, game_id)
    assert upgrade_id in result.activated_upgrade_ids

    async with async_session_factory() as db:
        upgrade = await db.get(StationUpgrade, upgrade_id)
        assert upgrade is not None
        assert upgrade.status == UpgradeStatus.ACTIVE
        assert effective_upgrade_level(upgrade) == 1

        after_fuel = (
            await db.execute(
                select(StationFuel).where(
                    StationFuel.game_station_id == station_id,
                    StationFuel.fuel_type == FuelType.AI92,
                )
            )
        ).scalar_one()
        assert after_fuel.capacity_liters > before_capacity


async def test_tick_activates_rating_upgrade_and_clamps_at_five(db_session: AsyncSession) -> None:
    game_id, station_id, owner_id = await _setup_owned_station("TickRating")

    async with async_session_factory() as db:
        station = await db.get(GameStation, station_id)
        assert station is not None
        station.rating = 4.95
        await db.commit()

    async with async_session_factory() as db:
        upgrade = await purchase_upgrade(db, game_id, owner_id, station_id, UpgradeType.RATING)
        upgrade_id = upgrade.id

    async with async_session_factory() as db:
        upgrade = await db.get(StationUpgrade, upgrade_id)
        assert upgrade is not None
        upgrade.completed_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

    async with async_session_factory() as db:
        await complete_due_upgrades_for_game(db, game_id)

    async with async_session_factory() as db:
        station = await db.get(GameStation, station_id)
        assert station is not None
        assert station.rating <= 5.0


async def test_tick_expires_advertising_after_campaign_window(db_session: AsyncSession) -> None:
    game_id, station_id, owner_id = await _setup_owned_station("TickAds")

    async with async_session_factory() as db:
        upgrade = await purchase_upgrade(db, game_id, owner_id, station_id, UpgradeType.ADVERTISING)
        upgrade_id = upgrade.id

    async with async_session_factory() as db:
        upgrade = await db.get(StationUpgrade, upgrade_id)
        assert upgrade is not None
        upgrade.completed_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

    async with async_session_factory() as db:
        result = await complete_due_upgrades_for_game(db, game_id)
    assert upgrade_id in result.activated_upgrade_ids

    async with async_session_factory() as db:
        upgrade = await db.get(StationUpgrade, upgrade_id)
        assert upgrade is not None
        assert upgrade.status == UpgradeStatus.ACTIVE
        # Simulate the campaign window (another build_minutes-long stretch) elapsing.
        upgrade.completed_at = datetime.now(UTC) - timedelta(minutes=20)
        await db.commit()

    async with async_session_factory() as db:
        result = await complete_due_upgrades_for_game(db, game_id)
    assert upgrade_id in result.expired_upgrade_ids

    async with async_session_factory() as db:
        upgrade = await db.get(StationUpgrade, upgrade_id)
        assert upgrade is not None
        assert upgrade.status == UpgradeStatus.EXPIRED
        assert effective_upgrade_level(upgrade) == 0


def test_effective_upgrade_level_under_construction_keeps_previous_level() -> None:
    upgrade = StationUpgrade(
        game_id=uuid.uuid4(),
        station_id=uuid.uuid4(),
        upgrade_type=UpgradeType.PUMPS,
        level=2,
        status=UpgradeStatus.UNDER_CONSTRUCTION,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    assert effective_upgrade_level(upgrade) == 1


def test_effective_upgrade_level_first_purchase_under_construction_is_zero() -> None:
    upgrade = StationUpgrade(
        game_id=uuid.uuid4(),
        station_id=uuid.uuid4(),
        upgrade_type=UpgradeType.PUMPS,
        level=1,
        status=UpgradeStatus.UNDER_CONSTRUCTION,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    assert effective_upgrade_level(upgrade) == 0
