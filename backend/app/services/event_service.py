import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.financial_transaction import (
    TRANSACTION_TYPE_EVENT_FINE,
    FinancialTransaction,
)
from app.db.models.game_event import EventStatus, EventType, GameEvent
from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom, GameStatus
from app.db.models.game_station import STATION_STATUS_ACTIVE, STATION_STATUS_INACTIVE, GameStation
from app.db.models.refinery_fuel import RefineryFuel
from app.db.models.road_edge import RoadEdge
from app.db.models.station_upgrade import StationUpgrade, UpgradeStatus
from app.schemas.game_settings import EventModifiers, GameSettings


class GameNotFoundError(Exception):
    pass


class GameNotRunningError(Exception):
    pass


class NotAGameMemberError(Exception):
    pass


class NotGameAdminError(Exception):
    pass


async def list_active_events(db: AsyncSession, game_id: uuid.UUID) -> list[GameEvent]:
    events = (
        (
            await db.execute(
                select(GameEvent).where(
                    GameEvent.game_id == game_id, GameEvent.status == EventStatus.ACTIVE
                )
            )
        )
        .scalars()
        .all()
    )
    return list(events)


async def list_event_history(db: AsyncSession, game_id: uuid.UUID) -> list[GameEvent]:
    events = (
        (
            await db.execute(
                select(GameEvent)
                .where(GameEvent.game_id == game_id)
                .order_by(GameEvent.started_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(events)


@dataclass(frozen=True)
class Region:
    latitude: float
    longitude: float
    radius_km: float


@dataclass(frozen=True)
class AttractivenessBonus:
    bonus: float
    region: Region | None
    required_upgrade_types: list[str]


def _merge_multipliers(events: list[GameEvent]) -> EventModifiers:
    """Multiplicatively combine the game-wide multiplier fields across all
    active events; the spatial/conditional attractiveness bonus is handled
    separately by ``list_attractiveness_bonuses`` since it needs per-station
    evaluation (region distance, required upgrades)."""
    traffic = 1.0
    spawn = 1.0
    refuel = 1.0
    refinery_price = 1.0
    price_sensitivity = 1.0
    ancillary = 1.0
    for event in events:
        modifiers = EventModifiers.model_validate(event.modifiers_json)
        traffic *= modifiers.traffic_multiplier
        spawn *= modifiers.vehicle_spawn_multiplier
        refuel *= modifiers.refuel_threshold_multiplier
        refinery_price *= modifiers.refinery_price_multiplier
        price_sensitivity *= modifiers.price_sensitivity_multiplier
        ancillary *= modifiers.ancillary_revenue_multiplier
    return EventModifiers(
        traffic_multiplier=traffic,
        vehicle_spawn_multiplier=spawn,
        refuel_threshold_multiplier=refuel,
        refinery_price_multiplier=refinery_price,
        price_sensitivity_multiplier=price_sensitivity,
        ancillary_revenue_multiplier=ancillary,
    )


def list_attractiveness_bonuses(events: list[GameEvent]) -> list[AttractivenessBonus]:
    bonuses: list[AttractivenessBonus] = []
    for event in events:
        modifiers = EventModifiers.model_validate(event.modifiers_json)
        if modifiers.attractiveness_bonus <= 0:
            continue
        region = Region(**event.region_json) if event.region_json else None
        bonuses.append(
            AttractivenessBonus(
                bonus=modifiers.attractiveness_bonus,
                region=region,
                required_upgrade_types=modifiers.attractiveness_upgrade_types,
            )
        )
    return bonuses


async def get_active_event_effects(
    db: AsyncSession, game_id: uuid.UUID
) -> tuple[EventModifiers, list[AttractivenessBonus]]:
    events = await list_active_events(db, game_id)
    return _merge_multipliers(events), list_attractiveness_bonuses(events)


async def _pick_region(db: AsyncSession, game_id: uuid.UUID, radius_km: float) -> dict[str, float]:
    station = (
        await db.execute(
            select(GameStation)
            .where(GameStation.game_id == game_id)
            .options(selectinload(GameStation.station_template))
            .order_by(func.random())
            .limit(1)
        )
    ).scalar_one_or_none()
    if station is None:
        return {"latitude": 56.6389, "longitude": 47.8845, "radius_km": radius_km}

    return {
        "latitude": station.station_template.latitude,
        "longitude": station.station_template.longitude,
        "radius_km": radius_km,
    }


async def _close_random_road_edge(db: AsyncSession, rng: random.Random) -> list[uuid.UUID]:
    open_edges = (
        (await db.execute(select(RoadEdge).where(RoadEdge.is_closed.is_(False)))).scalars().all()
    )
    if not open_edges:
        return []
    chosen = rng.choice(open_edges)
    closed_ids = [chosen.id]
    chosen.is_closed = True

    reverse = (
        await db.execute(
            select(RoadEdge).where(
                RoadEdge.from_node_id == chosen.to_node_id,
                RoadEdge.to_node_id == chosen.from_node_id,
            )
        )
    ).scalar_one_or_none()
    if reverse is not None and not reverse.is_closed:
        reverse.is_closed = True
        closed_ids.append(reverse.id)

    return closed_ids


async def _inspect_stations(
    db: AsyncSession,
    game_id: uuid.UUID,
    count: int,
    fine_amount: Decimal,
    rng: random.Random,
) -> list[uuid.UUID]:
    owned_stations = (
        (
            await db.execute(
                select(GameStation).where(
                    GameStation.game_id == game_id,
                    GameStation.owner_player_id.is_not(None),
                    GameStation.status == STATION_STATUS_ACTIVE,
                )
            )
        )
        .scalars()
        .all()
    )
    if not owned_stations:
        return []

    sample = rng.sample(owned_stations, k=min(count, len(owned_stations)))
    fined_ids: list[uuid.UUID] = []

    for station in sample:
        active_upgrade_count = (
            await db.execute(
                select(func.count())
                .select_from(StationUpgrade)
                .where(
                    StationUpgrade.station_id == station.id,
                    StationUpgrade.status == UpgradeStatus.ACTIVE,
                )
            )
        ).scalar_one()
        if active_upgrade_count > 0:
            continue

        assert station.owner_player_id is not None
        player = (
            await db.execute(
                select(GamePlayer).where(GamePlayer.id == station.owner_player_id).with_for_update()
            )
        ).scalar_one_or_none()
        if player is None:
            continue

        balance_before = player.balance
        fine = min(fine_amount, balance_before)
        player.balance = balance_before - fine
        db.add(
            FinancialTransaction(
                game_id=game_id,
                player_id=player.id,
                transaction_type=TRANSACTION_TYPE_EVENT_FINE,
                amount=-fine,
                balance_before=balance_before,
                balance_after=player.balance,
                reference_type="game_station",
                reference_id=station.id,
            )
        )
        station.status = STATION_STATUS_INACTIVE
        fined_ids.append(station.id)

    return fined_ids


async def _reduce_refinery_stock(db: AsyncSession, game_id: uuid.UUID, ratio: float) -> None:
    fuels = (
        (await db.execute(select(RefineryFuel).where(RefineryFuel.game_id == game_id)))
        .scalars()
        .all()
    )
    for fuel in fuels:
        fuel.current_liters = fuel.current_liters * Decimal(str(1 - ratio))


async def create_event_for_game(
    db: AsyncSession,
    game_id: uuid.UUID,
    room_settings: GameSettings,
    event_type: EventType,
    *,
    rng: random.Random | None = None,
) -> GameEvent:
    """Apply one-time effects and record a new active GameEvent.

    No permission checks here — used both by the admin manual-trigger path
    (``trigger_event``, after its own checks) and by the automatic batch
    roller (``app.simulation.events.roll_random_event_for_game``).
    """
    rng = rng or random.Random()
    definition = room_settings.event_definitions[event_type.value]

    now = datetime.now(UTC)
    ends_at = now + timedelta(seconds=definition.duration_seconds)

    region_json = None
    if definition.regional:
        region_json = await _pick_region(db, game_id, room_settings.event_region_radius_km)

    modifiers_extra: dict[str, list[str]] = {}
    if definition.close_random_edge:
        closed_ids = await _close_random_road_edge(db, rng)
        if closed_ids:
            modifiers_extra["closed_edge_ids"] = [str(edge_id) for edge_id in closed_ids]

    if definition.inspect_station_count > 0:
        fined_ids = await _inspect_stations(
            db, game_id, definition.inspect_station_count, definition.fine_amount, rng
        )
        if fined_ids:
            modifiers_extra["fined_station_ids"] = [str(station_id) for station_id in fined_ids]

    if definition.stock_loss_ratio > 0:
        await _reduce_refinery_stock(db, game_id, definition.stock_loss_ratio)

    modifiers_json = definition.modifiers.model_dump(mode="json")
    modifiers_json.update(modifiers_extra)

    event = GameEvent(
        game_id=game_id,
        event_type=event_type,
        status=EventStatus.ACTIVE,
        region_json=region_json,
        modifiers_json=modifiers_json,
        started_at=now,
        ends_at=ends_at,
    )
    db.add(event)

    await db.commit()
    await db.refresh(event)
    return event


async def trigger_event(
    db: AsyncSession,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
    event_type: EventType,
    *,
    rng: random.Random | None = None,
) -> GameEvent:
    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError
    if game.status != GameStatus.RUNNING:
        raise GameNotRunningError

    player = (
        await db.execute(
            select(GamePlayer).where(GamePlayer.game_id == game_id, GamePlayer.user_id == user_id)
        )
    ).scalar_one_or_none()
    if player is None:
        raise NotAGameMemberError
    if not player.is_admin:
        raise NotGameAdminError

    room_settings = GameSettings.model_validate(game.settings_json)
    return await create_event_for_game(db, game_id, room_settings, event_type, rng=rng)
