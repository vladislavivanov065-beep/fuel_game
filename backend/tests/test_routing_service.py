import uuid

import pytest

from app.services.routing_service import (
    EmptyGraphError,
    GraphEdge,
    GraphNode,
    NoRouteFoundError,
    build_multi_stop_route,
    find_nearest_node,
    find_route,
    greedy_nearest_neighbor_order,
    haversine_km,
)

NODE_A = uuid.uuid4()
NODE_B = uuid.uuid4()
NODE_C = uuid.uuid4()
NODE_D = uuid.uuid4()


def _nodes() -> list[GraphNode]:
    return [
        GraphNode(id=NODE_A, latitude=56.0, longitude=47.0),
        GraphNode(id=NODE_B, latitude=56.01, longitude=47.0),
        GraphNode(id=NODE_C, latitude=56.02, longitude=47.0),
        GraphNode(id=NODE_D, latitude=56.01, longitude=47.05),
    ]


def _two_way_edges(
    from_id: uuid.UUID,
    to_id: uuid.UUID,
    distance_km: float,
    max_speed_kmh: float = 60.0,
    is_closed: bool = False,
) -> list[GraphEdge]:
    return [
        GraphEdge(
            id=uuid.uuid4(),
            from_node_id=from_id,
            to_node_id=to_id,
            distance_km=distance_km,
            max_speed_kmh=max_speed_kmh,
            traffic_coefficient=1.0,
            is_closed=is_closed,
        ),
        GraphEdge(
            id=uuid.uuid4(),
            from_node_id=to_id,
            to_node_id=from_id,
            distance_km=distance_km,
            max_speed_kmh=max_speed_kmh,
            traffic_coefficient=1.0,
            is_closed=is_closed,
        ),
    ]


def test_haversine_km_matches_known_distance() -> None:
    # Roughly 1 degree of latitude is about 111 km.
    distance = haversine_km(56.0, 47.0, 57.0, 47.0)
    assert 110 < distance < 112


def test_find_nearest_node_picks_closest() -> None:
    nodes = _nodes()
    nearest = find_nearest_node(nodes, 56.019, 47.0)
    assert nearest.id == NODE_C


def test_find_nearest_node_raises_for_empty_graph() -> None:
    with pytest.raises(EmptyGraphError):
        find_nearest_node([], 56.0, 47.0)


def test_find_route_along_direct_path() -> None:
    nodes = _nodes()
    edges = _two_way_edges(NODE_A, NODE_B, 10.0) + _two_way_edges(NODE_B, NODE_C, 10.0)

    result = find_route(nodes, edges, NODE_A, NODE_C)

    assert result.distance_km == 20.0
    assert result.travel_time_minutes == pytest.approx(20.0)
    assert len(result.points) == 3


def test_find_route_same_start_and_end_is_trivial() -> None:
    nodes = _nodes()
    edges = _two_way_edges(NODE_A, NODE_B, 10.0)

    result = find_route(nodes, edges, NODE_A, NODE_A)

    assert result.distance_km == 0.0
    assert result.travel_time_minutes == 0.0


def test_find_route_raises_when_disconnected() -> None:
    nodes = _nodes()
    edges = _two_way_edges(NODE_A, NODE_B, 10.0)

    with pytest.raises(NoRouteFoundError):
        find_route(nodes, edges, NODE_A, NODE_C)


def test_find_route_detours_around_closed_edge() -> None:
    nodes = _nodes()
    edges = (
        _two_way_edges(NODE_A, NODE_B, 10.0)
        + _two_way_edges(NODE_B, NODE_C, 10.0, is_closed=True)
        + _two_way_edges(NODE_A, NODE_D, 8.0)
        + _two_way_edges(NODE_D, NODE_C, 8.0)
    )

    result = find_route(nodes, edges, NODE_A, NODE_C)

    assert result.distance_km == pytest.approx(16.0)


def test_find_route_exposes_per_segment_breakdown() -> None:
    nodes = _nodes()
    edges = _two_way_edges(NODE_A, NODE_B, 10.0) + _two_way_edges(NODE_B, NODE_C, 5.0)

    result = find_route(nodes, edges, NODE_A, NODE_C)

    assert result.segment_distances_km == [10.0, 5.0]
    assert result.segment_travel_times_minutes == pytest.approx([10.0, 5.0])


def test_build_multi_stop_route_accumulates_across_legs() -> None:
    nodes = _nodes()
    edges = (
        _two_way_edges(NODE_A, NODE_B, 10.0)
        + _two_way_edges(NODE_B, NODE_C, 10.0)
        + _two_way_edges(NODE_C, NODE_D, 5.0)
    )

    route = build_multi_stop_route(nodes, edges, [NODE_A, NODE_B, NODE_D])

    assert route.total_distance_km == pytest.approx(25.0)
    assert route.total_travel_time_minutes == pytest.approx(25.0)
    assert len(route.stop_point_indices) == 2
    first_stop_point = route.points[route.stop_point_indices[0]]
    assert first_stop_point.cumulative_km == pytest.approx(10.0)
    last_stop_point = route.points[route.stop_point_indices[1]]
    assert last_stop_point.cumulative_km == pytest.approx(25.0)


def test_build_multi_stop_route_handles_a_waypoint_that_repeats_the_previous_one() -> None:
    """A middle waypoint identical to the one before it (e.g. a chosen
    station's nearest node happens to equal the previous stop) is a trivial,
    zero-distance leg — it must not crash the cumulative-points chaining."""
    nodes = _nodes()
    edges = _two_way_edges(NODE_A, NODE_B, 10.0) + _two_way_edges(NODE_B, NODE_C, 10.0)

    route = build_multi_stop_route(nodes, edges, [NODE_A, NODE_B, NODE_B, NODE_C])

    assert route.total_distance_km == pytest.approx(20.0)
    assert len(route.stop_point_indices) == 3
    # The repeated waypoint contributes no new point, so its stop index
    # equals the previous stop's index.
    assert route.stop_point_indices[0] == route.stop_point_indices[1]


def test_build_multi_stop_route_requires_at_least_two_waypoints() -> None:
    nodes = _nodes()
    with pytest.raises(NoRouteFoundError):
        build_multi_stop_route(nodes, [], [NODE_A])


def test_greedy_nearest_neighbor_order_visits_closest_first() -> None:
    nodes = _nodes()
    edges = (
        _two_way_edges(NODE_A, NODE_B, 10.0)
        + _two_way_edges(NODE_A, NODE_C, 30.0)
        + _two_way_edges(NODE_B, NODE_C, 10.0)
    )

    order = greedy_nearest_neighbor_order(nodes, edges, NODE_A, [("far", NODE_C), ("near", NODE_B)])

    assert order == ["near", "far"]


def test_greedy_nearest_neighbor_order_raises_when_unreachable() -> None:
    nodes = _nodes()
    edges = _two_way_edges(NODE_A, NODE_B, 10.0)

    with pytest.raises(NoRouteFoundError):
        greedy_nearest_neighbor_order(nodes, edges, NODE_A, [("unreachable", NODE_C)])
