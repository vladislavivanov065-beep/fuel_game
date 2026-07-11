import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.refinery import Refinery
from app.db.models.refinery_fuel import RefineryFuel
from app.db.models.station_fuel import FuelType
from app.schemas.game_settings import GameSettings


def _default_purchase_prices(room_settings: GameSettings) -> dict[FuelType, Decimal]:
    return {
        FuelType.AI92: room_settings.refinery_ai92_purchase_price,
        FuelType.AI95: room_settings.refinery_ai95_purchase_price,
        FuelType.DIESEL: room_settings.refinery_diesel_purchase_price,
    }


async def create_refinery_fuels_for_game(
    db: AsyncSession, game_id: uuid.UUID, room_settings: GameSettings
) -> int:
    refineries = (await db.execute(select(Refinery))).scalars().all()
    purchase_prices = _default_purchase_prices(room_settings)

    objects = [
        RefineryFuel(
            refinery_id=refinery.id,
            game_id=game_id,
            fuel_type=fuel_type,
            current_liters=room_settings.refinery_starting_stock_liters,
            purchase_price=purchase_price,
            loading_speed=room_settings.refinery_loading_speed_liters_per_minute,
        )
        for refinery in refineries
        for fuel_type, purchase_price in purchase_prices.items()
    ]
    db.add_all(objects)
    return len(objects)


async def ensure_refinery(
    db: AsyncSession, name: str, latitude: float, longitude: float
) -> Refinery:
    existing = (
        await db.execute(select(Refinery).where(Refinery.name == name))
    ).scalar_one_or_none()
    if existing is not None:
        existing.latitude = latitude
        existing.longitude = longitude
        await db.commit()
        await db.refresh(existing)
        return existing

    refinery = Refinery(name=name, latitude=latitude, longitude=longitude)
    db.add(refinery)
    await db.commit()
    await db.refresh(refinery)
    return refinery


async def list_refineries(db: AsyncSession) -> list[Refinery]:
    result = await db.execute(select(Refinery).order_by(Refinery.name))
    return list(result.scalars())


@dataclass(frozen=True)
class RefineryWithFuels:
    refinery: Refinery
    fuels: list[RefineryFuel]


async def list_refineries_with_fuel_for_game(
    db: AsyncSession, game_id: uuid.UUID
) -> list[RefineryWithFuels]:
    refineries = await list_refineries(db)
    fuel_rows = (
        (await db.execute(select(RefineryFuel).where(RefineryFuel.game_id == game_id)))
        .scalars()
        .all()
    )

    fuels_by_refinery: dict[uuid.UUID, list[RefineryFuel]] = defaultdict(list)
    for fuel in fuel_rows:
        fuels_by_refinery[fuel.refinery_id].append(fuel)

    return [
        RefineryWithFuels(refinery=refinery, fuels=fuels_by_refinery.get(refinery.id, []))
        for refinery in refineries
    ]
