import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.game_room import GameRoom, GameStatus
from app.db.models.game_station import GameStation
from app.db.models.station_fuel import StationFuel
from app.db.models.station_upgrade import StationUpgrade, UpgradeStatus, UpgradeType
from app.schemas.game_settings import GameSettings

_MAX_RATING = 5.0


def effective_upgrade_level(upgrade: StationUpgrade) -> int:
    """The level whose bonus is actually live right now.

    While a subsequent level is under construction, the previously
    completed level's bonus stays in effect (the station keeps operating
    during the upgrade work), so this returns ``level - 1`` in that case.
    """
    if upgrade.status == UpgradeStatus.ACTIVE:
        return upgrade.level
    if upgrade.status == UpgradeStatus.EXPIRED:
        return 0
    return max(0, upgrade.level - 1)


async def get_active_upgrade_levels(
    db: AsyncSession, station_id: uuid.UUID
) -> dict[UpgradeType, int]:
    upgrades = (
        await db.execute(select(StationUpgrade).where(StationUpgrade.station_id == station_id))
    ).scalars()
    return {upgrade.upgrade_type: effective_upgrade_level(upgrade) for upgrade in upgrades}


@dataclass(frozen=True)
class UpgradeTickResult:
    activated_upgrade_ids: list[uuid.UUID]
    expired_upgrade_ids: list[uuid.UUID]


async def _apply_one_time_activation_effect(
    db: AsyncSession, upgrade: StationUpgrade, room_settings: GameSettings
) -> None:
    """Durable, additive effect applied once when a level finishes construction.

    Only TANKS (extra tank capacity) and RATING (a direct rating boost) are
    durable stat changes; the other upgrade types instead contribute to
    per-tick score/revenue calculations (see app/simulation/vehicles.py).
    """
    type_settings = room_settings.station_upgrades[upgrade.upgrade_type.value]

    if upgrade.upgrade_type == UpgradeType.TANKS:
        extra_liters = Decimal(str(type_settings.bonus_per_level))
        await db.execute(
            update(StationFuel)
            .where(StationFuel.game_station_id == upgrade.station_id)
            .values(capacity_liters=StationFuel.capacity_liters + extra_liters)
        )
    elif upgrade.upgrade_type == UpgradeType.RATING:
        new_rating = func.least(_MAX_RATING, GameStation.rating + type_settings.bonus_per_level)
        await db.execute(
            update(GameStation)
            .where(GameStation.id == upgrade.station_id)
            .values(rating=new_rating)
        )


async def complete_due_upgrades_for_game(db: AsyncSession, game_id: uuid.UUID) -> UpgradeTickResult:
    """Batch-advance every station upgrade for one running game.

    Called from the scheduler's batch loop (no background task per
    upgrade): flips UNDER_CONSTRUCTION -> ACTIVE once ``completed_at`` has
    passed (applying durable one-time effects for TANKS/RATING), and
    ACTIVE -> EXPIRED for ADVERTISING once its campaign window has elapsed
    (advertising "works for a limited time", TECHNICAL_SPEC.md section 19.5).
    """
    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None or game.status != GameStatus.RUNNING:
        return UpgradeTickResult(activated_upgrade_ids=[], expired_upgrade_ids=[])

    room_settings = GameSettings.model_validate(game.settings_json)
    now = datetime.now(UTC)

    upgrades = (
        await db.execute(
            select(StationUpgrade)
            .where(
                StationUpgrade.game_id == game_id,
                StationUpgrade.status != UpgradeStatus.EXPIRED,
            )
            .with_for_update()
        )
    ).scalars()

    activated_ids: list[uuid.UUID] = []
    expired_ids: list[uuid.UUID] = []

    for upgrade in upgrades:
        if upgrade.status == UpgradeStatus.UNDER_CONSTRUCTION:
            if now < upgrade.completed_at:
                continue
            upgrade.status = UpgradeStatus.ACTIVE
            activated_ids.append(upgrade.id)
            await _apply_one_time_activation_effect(db, upgrade, room_settings)
            continue

        if upgrade.upgrade_type != UpgradeType.ADVERTISING:
            continue
        type_settings = room_settings.station_upgrades[upgrade.upgrade_type.value]
        campaign_end = upgrade.completed_at + timedelta(minutes=type_settings.build_minutes)
        if now >= campaign_end:
            upgrade.status = UpgradeStatus.EXPIRED
            expired_ids.append(upgrade.id)

    await db.commit()
    return UpgradeTickResult(activated_upgrade_ids=activated_ids, expired_upgrade_ids=expired_ids)
