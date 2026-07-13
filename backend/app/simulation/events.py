import random
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.game_event import EventStatus, EventType, GameEvent
from app.db.models.game_room import GameRoom, GameStatus
from app.db.models.game_station import STATION_STATUS_ACTIVE, GameStation
from app.db.models.road_edge import RoadEdge
from app.schemas.game_settings import GameSettings
from app.services import event_service

_BASE_EVENT_PROBABILITY_PER_CHECK = 0.3


def _choose_weighted_event_type(
    room_settings: GameSettings, rng: random.Random
) -> EventType | None:
    entries = list(room_settings.event_definitions.items())
    total_weight = sum(definition.probability_weight for _, definition in entries)
    if total_weight <= 0:
        return None

    roll = rng.uniform(0, total_weight)
    cumulative = 0.0
    for event_type_value, definition in entries:
        cumulative += definition.probability_weight
        if roll <= cumulative:
            return EventType(event_type_value)
    return EventType(entries[-1][0])


async def roll_random_event_for_game(
    db: AsyncSession, game_id: uuid.UUID, *, rng: random.Random | None = None
) -> GameEvent | None:
    """Maybe start one new automatic event for a running game.

    Called from the scheduler's batch loop (no background task per game).
    Skips rolling while any event is already active for this game (a simple,
    global stand-in for TECHNICAL_SPEC.md's "minimum repeat interval" — an
    admin's manual trigger can still add a second, overlapping event).
    """
    rng = rng or random.Random()

    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None or game.status != GameStatus.RUNNING:
        return None

    has_active = (
        await db.execute(
            select(GameEvent.id).where(
                GameEvent.game_id == game_id, GameEvent.status == EventStatus.ACTIVE
            )
        )
    ).first()
    if has_active is not None:
        return None

    room_settings = GameSettings.model_validate(game.settings_json)

    last_event = (
        await db.execute(
            select(GameEvent)
            .where(GameEvent.game_id == game_id)
            .order_by(GameEvent.ends_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last_event is not None:
        seconds_since_last_ended = (datetime.now(UTC) - last_event.ends_at).total_seconds()
        if seconds_since_last_ended < room_settings.event_min_interval_seconds:
            return None

    if rng.random() >= room_settings.event_frequency * _BASE_EVENT_PROBABILITY_PER_CHECK:
        return None

    event_type = _choose_weighted_event_type(room_settings, rng)
    if event_type is None:
        return None

    return await event_service.create_event_for_game(
        db, game_id, room_settings, event_type, rng=rng
    )


async def _revert_one_time_effects(db: AsyncSession, event: GameEvent) -> None:
    closed_edge_ids = event.modifiers_json.get("closed_edge_ids", [])
    if closed_edge_ids:
        edges = (
            (
                await db.execute(
                    select(RoadEdge).where(RoadEdge.id.in_([uuid.UUID(i) for i in closed_edge_ids]))
                )
            )
            .scalars()
            .all()
        )
        for edge in edges:
            edge.is_closed = False

    fined_station_ids = event.modifiers_json.get("fined_station_ids", [])
    if fined_station_ids:
        stations = (
            (
                await db.execute(
                    select(GameStation).where(
                        GameStation.id.in_([uuid.UUID(i) for i in fined_station_ids])
                    )
                )
            )
            .scalars()
            .all()
        )
        for station in stations:
            station.status = STATION_STATUS_ACTIVE


async def expire_due_events_for_game(db: AsyncSession, game_id: uuid.UUID) -> list[uuid.UUID]:
    """Flip ACTIVE -> EXPIRED for events whose ``ends_at`` has passed and undo
    their one-time effects (reopen closed roads, reactivate fined stations)."""
    now = datetime.now(UTC)
    due_events = (
        (
            await db.execute(
                select(GameEvent).where(
                    GameEvent.game_id == game_id,
                    GameEvent.status == EventStatus.ACTIVE,
                    GameEvent.ends_at <= now,
                )
            )
        )
        .scalars()
        .all()
    )

    expired_ids: list[uuid.UUID] = []
    for event in due_events:
        event.status = EventStatus.EXPIRED
        await _revert_one_time_effects(db, event)
        expired_ids.append(event.id)

    if expired_ids:
        await db.commit()
    return expired_ids
