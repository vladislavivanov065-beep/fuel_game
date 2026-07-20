import math
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.simulation.traffic_lights import LightState

_METERS_PER_KMH_PER_SECOND = 1000.0 / 3600.0


def bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compass bearing (0=north, 90=east) from point 1 to point 2, for marker rotation."""
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lon_rad = math.radians(lon2 - lon1)
    x = math.sin(delta_lon_rad) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(
        lat2_rad
    ) * math.cos(delta_lon_rad)
    return math.degrees(math.atan2(x, y)) % 360


def position_within_edge(
    points: list[dict[str, Any]],
    route_edge_index: int,
    position_on_edge_m: float,
    edge_length_m: float,
) -> tuple[float, float, float]:
    """Interpolate lat/lon/heading within the edge ending at ``points[route_edge_index]``,
    given physically simulated distance along it (Этап 14.3) — shared by Vehicle and
    Truck, replacing three previously-independent elapsed-wall-clock-time
    interpolation implementations.
    """
    previous = points[route_edge_index - 1]
    current = points[route_edge_index]
    fraction = 0.0 if edge_length_m <= 0 else min(1.0, max(0.0, position_on_edge_m / edge_length_m))
    lat = previous["latitude"] + (current["latitude"] - previous["latitude"]) * fraction
    lon = previous["longitude"] + (current["longitude"] - previous["longitude"]) * fraction
    heading = bearing_degrees(
        previous["latitude"], previous["longitude"], current["latitude"], current["longitude"]
    )
    return lat, lon, heading


def route_progress(
    points: list[dict[str, Any]],
    route_edge_index: int,
    position_on_edge_m: float,
    total_distance_km: float,
) -> float:
    if total_distance_km <= 0:
        return 1.0
    distance_km_at_edge_start = float(points[route_edge_index - 1]["cumulative_km"])
    distance_km = distance_km_at_edge_start + position_on_edge_m / 1000.0
    return min(1.0, max(0.0, distance_km / total_distance_km))


def next_edge_id(points: list[dict[str, Any]], route_edge_index: int) -> uuid.UUID | None:
    next_index = route_edge_index + 1
    if next_index >= len(points):
        return None
    return uuid.UUID(points[next_index]["edge_id"])


@dataclass(frozen=True)
class EdgeInfo:
    length_m: float
    to_node_id: uuid.UUID
    max_speed_kmh: float
    traffic_coefficient: float


@dataclass(frozen=True)
class Mover:
    """A vehicle or truck currently on the road graph, for one physics step.

    ``key`` is an opaque caller-supplied identifier (e.g. the DB row id) used
    only to match results back to the right entity — this module knows
    nothing about Vehicle/Truck models, keeping it a pure, independently
    testable simulation core shared by both (Этап 14.3).
    """

    key: str
    current_edge_id: uuid.UUID
    position_on_edge_m: float
    velocity_kmh: float
    length_m: float
    is_emergency: bool
    next_edge_id: uuid.UUID | None  # None => arrives (route ends) at this edge's end
    speed_factor: float = 1.0  # per-vehicle-type multiplier on the edge's free speed


@dataclass(frozen=True)
class MoverResult:
    key: str
    edge_id: uuid.UUID
    position_on_edge_m: float
    velocity_kmh: float
    crossed_edge: bool
    arrived: bool


def _tail_position_m(occupants: list[Mover]) -> float | None:
    if not occupants:
        return None
    return min(mover.position_on_edge_m for mover in occupants)


def step_edge_occupants(
    movers: list[Mover],
    edges: dict[uuid.UUID, EdgeInfo],
    light_states: dict[uuid.UUID, LightState],
    *,
    dt_seconds: float,
    min_gap_m: float,
) -> list[MoverResult]:
    """Advance every mover by one simulation tick (car-following + traffic lights).

    Each edge's occupants are processed front-to-back (by position, descending):
    the front-most mover is limited only by the traffic light at the edge's end
    node and by whether the next edge has room to receive it (backpressure —
    this is what makes an accident/closure "back up" traffic onto earlier
    edges with no special-case code); every following mover is limited by the
    gap to the mover ahead of it on the same edge. Emergency vehicle types
    ignore both the light and the following/capacity gating ("едут по
    встречке").

    All "room on the next edge" and "light state" checks read a snapshot from
    the START of this tick (not other movers' just-computed results) — two
    movers converging onto the same edge from different source edges in the
    same tick may end up close together; a known, accepted simplification at
    this project's simulation fidelity (see Этап 14 known limitations).
    """
    by_edge: dict[uuid.UUID, list[Mover]] = defaultdict(list)
    for mover in movers:
        by_edge[mover.current_edge_id].append(mover)

    results: list[MoverResult] = []
    for edge_id, occupants in by_edge.items():
        edge = edges[edge_id]
        ordered = sorted(occupants, key=lambda mover: mover.position_on_edge_m, reverse=True)
        previous_position_m: float | None = None
        previous_length_m = 0.0

        for mover in ordered:
            free_speed_kmh = (
                edge.max_speed_kmh / max(edge.traffic_coefficient, 0.01) * mover.speed_factor
            )

            if mover.is_emergency or previous_position_m is None:
                target_speed_kmh = free_speed_kmh
            else:
                gap_m = (previous_position_m - previous_length_m) - mover.position_on_edge_m
                if gap_m <= 0:
                    target_speed_kmh = 0.0
                elif gap_m < min_gap_m:
                    target_speed_kmh = free_speed_kmh * (gap_m / min_gap_m)
                else:
                    target_speed_kmh = free_speed_kmh

            new_velocity_kmh = max(0.0, target_speed_kmh)
            advance_m = new_velocity_kmh * _METERS_PER_KMH_PER_SECOND * dt_seconds
            candidate_position_m = mover.position_on_edge_m + advance_m

            if not mover.is_emergency and previous_position_m is not None:
                max_allowed_m = previous_position_m - previous_length_m - min_gap_m
                candidate_position_m = min(
                    candidate_position_m, max(mover.position_on_edge_m, max_allowed_m)
                )

            if candidate_position_m < edge.length_m:
                results.append(
                    MoverResult(
                        key=mover.key,
                        edge_id=edge_id,
                        position_on_edge_m=candidate_position_m,
                        velocity_kmh=new_velocity_kmh,
                        crossed_edge=False,
                        arrived=False,
                    )
                )
                previous_position_m = candidate_position_m
                previous_length_m = mover.length_m
                continue

            if mover.next_edge_id is None:
                can_cross = True
            else:
                light_state = light_states.get(edge.to_node_id)
                light_blocks = not mover.is_emergency and light_state in (
                    LightState.RED,
                    LightState.YELLOW,
                )

                room_ahead = True
                if not mover.is_emergency:
                    next_edge = edges.get(mover.next_edge_id)
                    if next_edge is not None:
                        tail_m = _tail_position_m(by_edge.get(mover.next_edge_id, []))
                        if tail_m is not None and tail_m < min_gap_m:
                            room_ahead = False

                can_cross = mover.is_emergency or (not light_blocks and room_ahead)

            if not can_cross:
                stopped_position_m = min(candidate_position_m, edge.length_m)
                results.append(
                    MoverResult(
                        key=mover.key,
                        edge_id=edge_id,
                        position_on_edge_m=stopped_position_m,
                        velocity_kmh=0.0,
                        crossed_edge=False,
                        arrived=False,
                    )
                )
                previous_position_m = stopped_position_m
                previous_length_m = mover.length_m
                continue

            if mover.next_edge_id is None:
                results.append(
                    MoverResult(
                        key=mover.key,
                        edge_id=edge_id,
                        position_on_edge_m=edge.length_m,
                        velocity_kmh=new_velocity_kmh,
                        crossed_edge=False,
                        arrived=True,
                    )
                )
                previous_position_m = edge.length_m
                previous_length_m = mover.length_m
                continue

            overflow_m = candidate_position_m - edge.length_m
            results.append(
                MoverResult(
                    key=mover.key,
                    edge_id=mover.next_edge_id,
                    position_on_edge_m=overflow_m,
                    velocity_kmh=new_velocity_kmh,
                    crossed_edge=True,
                    arrived=False,
                )
            )
            previous_position_m = candidate_position_m
            previous_length_m = mover.length_m

    return results
