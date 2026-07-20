import heapq
import math
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode

_EARTH_RADIUS_KM = 6371.0


class EmptyGraphError(Exception):
    pass


class NoRouteFoundError(Exception):
    pass


@dataclass(frozen=True)
class GraphNode:
    id: uuid.UUID
    latitude: float
    longitude: float


@dataclass(frozen=True)
class GraphEdge:
    id: uuid.UUID
    from_node_id: uuid.UUID
    to_node_id: uuid.UUID
    distance_km: float
    max_speed_kmh: float
    traffic_coefficient: float
    is_closed: bool
    road_type: str
    trolleybus_wire: bool


@dataclass(frozen=True)
class RoutePoint:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class RouteResult:
    points: list[RoutePoint]
    distance_km: float
    travel_time_minutes: float
    segment_distances_km: list[float]
    segment_travel_times_minutes: list[float]
    segment_edge_ids: list[uuid.UUID]


@dataclass(frozen=True)
class AnnotatedPoint:
    latitude: float
    longitude: float
    cumulative_km: float
    cumulative_minutes: float
    edge_id: uuid.UUID | None


@dataclass(frozen=True)
class MultiStopRoute:
    points: list[AnnotatedPoint]
    stop_point_indices: list[int]
    total_distance_km: float
    total_travel_time_minutes: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def find_nearest_node(nodes: list[GraphNode], latitude: float, longitude: float) -> GraphNode:
    if not nodes:
        raise EmptyGraphError
    return min(
        nodes, key=lambda node: haversine_km(latitude, longitude, node.latitude, node.longitude)
    )


def _edge_travel_time_minutes(edge: GraphEdge) -> float:
    return (edge.distance_km / edge.max_speed_kmh) * 60.0 * edge.traffic_coefficient


def find_route(
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    start_node_id: uuid.UUID,
    end_node_id: uuid.UUID,
    *,
    edge_filter: Callable[[GraphEdge], bool] | None = None,
) -> RouteResult:
    """A* search over a directed graph, weighted by travel time.

    Edges with ``is_closed`` set are excluded from the search entirely, so a
    closed road is simply unreachable until it reopens. ``edge_filter``, if
    given, further restricts which edges may be used at all (Этап 14.4 — e.g.
    a trolleybus may only use ``trolleybus_wire`` edges, a cargo truck may not
    use certain ``road_type`` values) — an edge failing the filter is treated
    exactly like a closed one for this search.
    """
    nodes_by_id = {node.id: node for node in nodes}
    if start_node_id not in nodes_by_id or end_node_id not in nodes_by_id:
        raise NoRouteFoundError

    if start_node_id == end_node_id:
        node = nodes_by_id[start_node_id]
        point = RoutePoint(latitude=node.latitude, longitude=node.longitude)
        return RouteResult(
            points=[point, point],
            distance_km=0.0,
            travel_time_minutes=0.0,
            segment_distances_km=[],
            segment_travel_times_minutes=[],
            segment_edge_ids=[],
        )

    adjacency: dict[uuid.UUID, list[GraphEdge]] = defaultdict(list)
    for edge in edges:
        if not edge.is_closed and (edge_filter is None or edge_filter(edge)):
            adjacency[edge.from_node_id].append(edge)

    fastest_speed_kmh = max((edge.max_speed_kmh for edge in edges), default=60.0)
    end_node = nodes_by_id[end_node_id]

    def heuristic(node_id: uuid.UUID) -> float:
        node = nodes_by_id[node_id]
        distance = haversine_km(
            node.latitude, node.longitude, end_node.latitude, end_node.longitude
        )
        return (distance / fastest_speed_kmh) * 60.0

    open_heap: list[tuple[float, uuid.UUID]] = [(heuristic(start_node_id), start_node_id)]
    g_score: dict[uuid.UUID, float] = {start_node_id: 0.0}
    came_from: dict[uuid.UUID, tuple[uuid.UUID, GraphEdge]] = {}
    visited: set[uuid.UUID] = set()

    while open_heap:
        _, current_id = heapq.heappop(open_heap)
        if current_id in visited:
            continue
        if current_id == end_node_id:
            break
        visited.add(current_id)

        for edge in adjacency.get(current_id, []):
            neighbor_id = edge.to_node_id
            tentative_g = g_score[current_id] + _edge_travel_time_minutes(edge)
            if tentative_g < g_score.get(neighbor_id, math.inf):
                g_score[neighbor_id] = tentative_g
                came_from[neighbor_id] = (current_id, edge)
                heapq.heappush(open_heap, (tentative_g + heuristic(neighbor_id), neighbor_id))

    if end_node_id not in g_score:
        raise NoRouteFoundError

    path_node_ids: list[uuid.UUID] = [end_node_id]
    path_edges: list[GraphEdge] = []
    cursor = end_node_id
    while cursor != start_node_id:
        prev_id, edge = came_from[cursor]
        path_edges.append(edge)
        path_node_ids.append(prev_id)
        cursor = prev_id
    path_node_ids.reverse()
    path_edges.reverse()

    points = [
        RoutePoint(latitude=nodes_by_id[node_id].latitude, longitude=nodes_by_id[node_id].longitude)
        for node_id in path_node_ids
    ]
    segment_distances_km = [edge.distance_km for edge in path_edges]
    segment_travel_times_minutes = [_edge_travel_time_minutes(edge) for edge in path_edges]
    segment_edge_ids = [edge.id for edge in path_edges]

    return RouteResult(
        points=points,
        distance_km=sum(segment_distances_km),
        travel_time_minutes=sum(segment_travel_times_minutes),
        segment_distances_km=segment_distances_km,
        segment_travel_times_minutes=segment_travel_times_minutes,
        segment_edge_ids=segment_edge_ids,
    )


def build_multi_stop_route(
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    waypoint_node_ids: list[uuid.UUID],
    *,
    edge_filter: Callable[[GraphEdge], bool] | None = None,
) -> MultiStopRoute:
    """Chain consecutive A* legs into one route, annotated with running totals.

    ``waypoint_node_ids[0]`` is the starting point (the refinery); every
    following id is a stop, in visiting order. Each point in the resulting
    route carries the cumulative distance/time from the start, so the
    scheduler can find a truck's position by elapsed time alone.
    """
    if len(waypoint_node_ids) < 2:
        raise NoRouteFoundError

    nodes_by_id = {node.id: node for node in nodes}
    start_node = nodes_by_id.get(waypoint_node_ids[0])
    if start_node is None:
        raise NoRouteFoundError

    points: list[AnnotatedPoint] = [
        AnnotatedPoint(
            latitude=start_node.latitude,
            longitude=start_node.longitude,
            cumulative_km=0.0,
            cumulative_minutes=0.0,
            edge_id=None,
        )
    ]
    stop_point_indices: list[int] = []
    cumulative_km = 0.0
    cumulative_minutes = 0.0

    for i in range(len(waypoint_node_ids) - 1):
        leg = find_route(
            nodes, edges, waypoint_node_ids[i], waypoint_node_ids[i + 1], edge_filter=edge_filter
        )
        # A trivial leg (waypoint == next waypoint) returns two identical
        # points but empty segment lists; zip stops at the shorter (empty)
        # side, so no new point is added and the stop simply reuses the
        # previous point — correct, since nothing moved.
        for point, segment_km, segment_minutes, edge_id in zip(
            leg.points[1:],
            leg.segment_distances_km,
            leg.segment_travel_times_minutes,
            leg.segment_edge_ids,
            strict=False,
        ):
            cumulative_km += segment_km
            cumulative_minutes += segment_minutes
            points.append(
                AnnotatedPoint(
                    latitude=point.latitude,
                    longitude=point.longitude,
                    cumulative_km=cumulative_km,
                    cumulative_minutes=cumulative_minutes,
                    edge_id=edge_id,
                )
            )
        stop_point_indices.append(len(points) - 1)

    return MultiStopRoute(
        points=points,
        stop_point_indices=stop_point_indices,
        total_distance_km=cumulative_km,
        total_travel_time_minutes=cumulative_minutes,
    )


def greedy_nearest_neighbor_order[StopKey](
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    start_node_id: uuid.UUID,
    stops: list[tuple[StopKey, uuid.UUID]],
) -> list[StopKey]:
    """Order stops by repeatedly picking the closest remaining one by travel time.

    This is the MVP "nearest neighbor" heuristic called for in the spec —
    not a full vehicle-routing optimization.
    """
    remaining = list(stops)
    ordered_keys: list[StopKey] = []
    current_node_id = start_node_id

    while remaining:
        best_index: int | None = None
        best_time = math.inf
        for index, (_, node_id) in enumerate(remaining):
            try:
                leg = find_route(nodes, edges, current_node_id, node_id)
            except NoRouteFoundError:
                continue
            if leg.travel_time_minutes < best_time:
                best_time = leg.travel_time_minutes
                best_index = index

        if best_index is None:
            raise NoRouteFoundError

        key, node_id = remaining.pop(best_index)
        ordered_keys.append(key)
        current_node_id = node_id

    return ordered_keys


def serialize_multi_stop_route(route: MultiStopRoute, positions: list[int]) -> dict[str, Any]:
    """Serialize a route to a JSON-able dict, ready for ``Truck.route_json``.

    ``positions`` pairs each entry in ``route.stop_point_indices`` with the
    ``FuelOrderStop.position`` it corresponds to — the two lists share an
    index but the position values themselves may be a non-contiguous subset
    (e.g. after a mid-trip reroute past already-delivered stops).
    """
    return {
        "points": [
            {
                "latitude": point.latitude,
                "longitude": point.longitude,
                "cumulative_km": point.cumulative_km,
                "cumulative_minutes": point.cumulative_minutes,
                "edge_id": str(point.edge_id) if point.edge_id is not None else None,
            }
            for point in route.points
        ],
        "stops": [
            {"position": position, "point_index": point_index}
            for position, point_index in zip(positions, route.stop_point_indices, strict=True)
        ],
        "total_distance_km": route.total_distance_km,
        "total_travel_time_minutes": route.total_travel_time_minutes,
    }


async def load_graph(
    db: AsyncSession, *, traffic_multiplier: float = 1.0
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Load the road graph, optionally scaling every edge's traffic
    coefficient in memory (e.g. a storm GameEvent) — never mutates the
    stored RoadEdge rows themselves."""
    node_rows = (await db.execute(select(RoadNode))).scalars().all()
    edge_rows = (await db.execute(select(RoadEdge))).scalars().all()

    nodes = [
        GraphNode(id=row.id, latitude=row.latitude, longitude=row.longitude) for row in node_rows
    ]
    edges = [
        GraphEdge(
            id=row.id,
            from_node_id=row.from_node_id,
            to_node_id=row.to_node_id,
            distance_km=row.distance_km,
            max_speed_kmh=row.max_speed_kmh,
            traffic_coefficient=row.traffic_coefficient * traffic_multiplier,
            is_closed=row.is_closed,
            road_type=row.road_type,
            trolleybus_wire=row.trolleybus_wire,
        )
        for row in edge_rows
    ]
    return nodes, edges


async def compute_route(
    db: AsyncSession,
    from_latitude: float,
    from_longitude: float,
    to_latitude: float,
    to_longitude: float,
) -> RouteResult:
    nodes, edges = await load_graph(db)
    start_node = find_nearest_node(nodes, from_latitude, from_longitude)
    end_node = find_nearest_node(nodes, to_latitude, to_longitude)
    return find_route(nodes, edges, start_node.id, end_node.id)
