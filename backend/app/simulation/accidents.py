import random
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.game_room import GameRoom
from app.db.models.road_accident import AccidentSeverity, RoadAccident
from app.db.models.road_edge import RoadEdge
from app.db.models.truck import Truck, TruckStatus
from app.db.models.vehicle import Vehicle, VehicleStatus
from app.schemas.game_settings import GameSettings

# Nominal metres of road one moving vehicle "occupies" (length + following
# gap), used only to turn a raw mover count into a 0..1 congestion estimate —
# not a physical constant, just a risk-scoring proxy (Этап 14.5).
_AVERAGE_VEHICLE_SPACING_M = 10.0


def edge_occupancy_ratio(mover_count: int, edge_length_m: float) -> float:
    """Pure, testable proxy for how congested an edge currently is.

    0 = empty, 1 = at (or beyond) nominal capacity. This is the sole input
    to accident risk — a busy edge is more likely to have an accident.
    """
    if edge_length_m <= 0:
        return 1.0
    capacity = max(1.0, edge_length_m / _AVERAGE_VEHICLE_SPACING_M)
    return min(1.0, mover_count / capacity)


def accident_probability_per_minute(
    occupancy_ratio: float, base_probability_per_minute: float
) -> float:
    """Risk scales linearly with congestion: an empty edge never has an
    accident, a fully jammed one hits the configured base rate."""
    return base_probability_per_minute * max(0.0, min(1.0, occupancy_ratio))


@dataclass(frozen=True)
class StartedAccident:
    accident_id: uuid.UUID
    road_edge_id: uuid.UUID
    severity: AccidentSeverity
    ends_at: datetime


@dataclass(frozen=True)
class EndedAccident:
    accident_id: uuid.UUID
    road_edge_id: uuid.UUID


async def _occupied_edge_counts(db: AsyncSession, game_id: uuid.UUID) -> Counter[uuid.UUID]:
    counts: Counter[uuid.UUID] = Counter()
    vehicle_edges = (
        await db.execute(
            select(Vehicle.current_edge_id).where(
                Vehicle.game_id == game_id,
                Vehicle.status == VehicleStatus.DRIVING,
                Vehicle.current_edge_id.is_not(None),
            )
        )
    ).scalars()
    for edge_id in vehicle_edges:
        if edge_id is not None:
            counts[edge_id] += 1

    truck_edges = (
        await db.execute(
            select(Truck.current_edge_id).where(
                Truck.game_id == game_id,
                Truck.status == TruckStatus.EN_ROUTE,
                Truck.current_edge_id.is_not(None),
            )
        )
    ).scalars()
    for edge_id in truck_edges:
        if edge_id is not None:
            counts[edge_id] += 1

    return counts


async def roll_accidents_for_game(
    db: AsyncSession,
    game_id: uuid.UUID,
    *,
    dt_seconds: float,
    rng: random.Random | None = None,
) -> list[StartedAccident]:
    """One accident risk roll per currently-occupied, non-closed edge.

    Independent of GameEvent by design (Этап 14 planning decision): no
    admin trigger, no event history — purely an emergent consequence of how
    congested the road network is right now.
    """
    rng = rng if rng is not None else random.Random()
    game = await db.get(GameRoom, game_id)
    if game is None:
        return []
    settings = GameSettings.model_validate(game.settings_json)

    counts = await _occupied_edge_counts(db, game_id)
    if not counts:
        return []

    edges = (
        (
            await db.execute(
                select(RoadEdge).where(
                    RoadEdge.id.in_(counts.keys()), RoadEdge.is_closed.is_(False)
                )
            )
        )
        .scalars()
        .all()
    )
    if not edges:
        return []

    now = datetime.now(UTC)
    active_edge_ids = set(
        (
            await db.execute(
                select(RoadAccident.road_edge_id).where(
                    RoadAccident.game_id == game_id, RoadAccident.ends_at > now
                )
            )
        ).scalars()
    )

    started: list[StartedAccident] = []
    for edge in edges:
        if edge.id in active_edge_ids:
            continue

        occupancy = edge_occupancy_ratio(counts[edge.id], edge.distance_km * 1000.0)
        probability_per_minute = accident_probability_per_minute(
            occupancy, settings.accident_base_probability_per_minute
        )
        probability_this_tick = probability_per_minute * (dt_seconds / 60.0)
        if rng.random() >= probability_this_tick:
            continue

        severity = (
            AccidentSeverity.MAJOR
            if rng.random() < settings.accident_major_probability
            else AccidentSeverity.MINOR
        )
        duration_seconds = rng.uniform(
            settings.accident_min_duration_seconds, settings.accident_max_duration_seconds
        )
        accident = RoadAccident(
            game_id=game_id,
            road_edge_id=edge.id,
            severity=severity,
            started_at=now,
            ends_at=now + timedelta(seconds=duration_seconds),
            previous_traffic_coefficient=edge.traffic_coefficient,
        )
        db.add(accident)

        if severity == AccidentSeverity.MAJOR:
            edge.is_closed = True
        else:
            edge.traffic_coefficient = (
                edge.traffic_coefficient * settings.accident_minor_traffic_penalty
            )

        await db.flush()
        started.append(
            StartedAccident(
                accident_id=accident.id,
                road_edge_id=edge.id,
                severity=severity,
                ends_at=accident.ends_at,
            )
        )

    if started:
        await db.commit()

    return started


async def expire_due_accidents_for_game(
    db: AsyncSession, game_id: uuid.UUID
) -> list[EndedAccident]:
    """Revert each expired accident's effect on its edge and remove it."""
    now = datetime.now(UTC)
    due = (
        (
            await db.execute(
                select(RoadAccident).where(
                    RoadAccident.game_id == game_id, RoadAccident.ends_at <= now
                )
            )
        )
        .scalars()
        .all()
    )
    if not due:
        return []

    ended: list[EndedAccident] = []
    for accident in due:
        edge = await db.get(RoadEdge, accident.road_edge_id)
        if edge is not None:
            if accident.severity == AccidentSeverity.MAJOR:
                edge.is_closed = False
            else:
                edge.traffic_coefficient = accident.previous_traffic_coefficient
        ended.append(EndedAccident(accident_id=accident.id, road_edge_id=accident.road_edge_id))
        await db.delete(accident)

    await db.commit()
    return ended
