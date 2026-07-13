from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.refinery import Refinery
from app.db.models.refinery_fuel import RefineryFuel
from app.db.models.station_fuel import FuelType
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.schemas.game_settings import GameSettings
from app.services.auth_service import register_user
from app.services.game_service import create_game
from app.services.refinery_service import (
    create_refinery_fuels_for_game,
    ensure_refinery,
    list_refineries,
)


async def test_ensure_refinery_creates_one_row(db_session: AsyncSession) -> None:
    refinery = await ensure_refinery(db_session, "Test Depot", 56.7, 47.9)

    assert refinery.name == "Test Depot"
    result = await db_session.execute(select(Refinery).where(Refinery.name == "Test Depot"))
    assert len(result.scalars().all()) == 1


async def test_ensure_refinery_is_idempotent(db_session: AsyncSession) -> None:
    await ensure_refinery(db_session, "Idempotent Depot", 56.7, 47.9)
    await ensure_refinery(db_session, "Idempotent Depot", 56.8, 48.0)

    result = await db_session.execute(select(Refinery).where(Refinery.name == "Idempotent Depot"))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].latitude == 56.8
    assert rows[0].longitude == 48.0


async def test_list_refineries_returns_all(db_session: AsyncSession) -> None:
    await ensure_refinery(db_session, "Depot A", 56.0, 47.0)
    await ensure_refinery(db_session, "Depot B", 57.0, 48.0)

    refineries = await list_refineries(db_session)

    names = {r.name for r in refineries}
    assert names == {"Depot A", "Depot B"}


async def test_create_refinery_fuels_for_game_seeds_all_fuel_types(
    db_session: AsyncSession,
) -> None:
    db_session.add_all(
        [
            Refinery(name="Refinery A", latitude=56.0, longitude=47.0),
            Refinery(name="Refinery B", latitude=56.2, longitude=47.2),
        ]
    )
    await db_session.commit()

    user, _ = await register_user(
        db_session,
        RegisterRequest(
            email="refinerysvc@example.com",
            password="correcthorsebattery",
            display_name="Owner",
        ),
    )
    game = await create_game(db_session, user.id, CreateGameRequest(name="Refinery Fuels Test"))
    game_id = game.id

    created = await create_refinery_fuels_for_game(db_session, game_id, GameSettings())
    await db_session.commit()

    assert created == 6

    rows = (
        (await db_session.execute(select(RefineryFuel).where(RefineryFuel.game_id == game_id)))
        .scalars()
        .all()
    )
    assert len(rows) == 6
    ai92_rows = [row for row in rows if row.fuel_type == FuelType.AI92]
    assert len(ai92_rows) == 2
    for row in ai92_rows:
        assert row.current_liters == Decimal("500000.00")
        assert row.purchase_price == Decimal("42.00")
        assert row.loading_speed == 2000.0
