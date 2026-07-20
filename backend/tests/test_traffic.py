import uuid

from app.simulation.traffic import EdgeInfo, Mover, step_edge_occupants
from app.simulation.traffic_lights import LightState

EDGE_A = uuid.uuid4()
EDGE_B = uuid.uuid4()
NODE_END_A = uuid.uuid4()


def _edge(length_m: float = 1000.0, max_speed_kmh: float = 36.0) -> EdgeInfo:
    # 36 km/h == 10 m/s, convenient for exact arithmetic in tests.
    return EdgeInfo(
        length_m=length_m,
        to_node_id=NODE_END_A,
        max_speed_kmh=max_speed_kmh,
        traffic_coefficient=1.0,
    )


def _mover(
    key: str,
    position_on_edge_m: float,
    *,
    edge_id: uuid.UUID = EDGE_A,
    velocity_kmh: float = 0.0,
    length_m: float = 4.5,
    is_emergency: bool = False,
    next_edge_id: uuid.UUID | None = EDGE_B,
) -> Mover:
    return Mover(
        key=key,
        current_edge_id=edge_id,
        position_on_edge_m=position_on_edge_m,
        velocity_kmh=velocity_kmh,
        length_m=length_m,
        is_emergency=is_emergency,
        next_edge_id=next_edge_id,
    )


def test_lone_mover_accelerates_to_free_speed_and_advances() -> None:
    edges = {EDGE_A: _edge(length_m=1000.0)}
    movers = [_mover("v1", 0.0)]

    results = step_edge_occupants(movers, edges, {}, dt_seconds=1.0, min_gap_m=3.0)

    assert len(results) == 1
    result = results[0]
    assert result.velocity_kmh == 36.0
    assert result.position_on_edge_m == 10.0
    assert not result.crossed_edge
    assert not result.arrived


def test_mover_stops_at_red_light_at_edge_end() -> None:
    edges = {EDGE_A: _edge(length_m=5.0), EDGE_B: _edge(length_m=1000.0)}
    movers = [_mover("v1", 0.0)]
    light_states = {NODE_END_A: LightState.RED}

    results = step_edge_occupants(movers, edges, light_states, dt_seconds=1.0, min_gap_m=3.0)

    assert len(results) == 1
    result = results[0]
    assert result.edge_id == EDGE_A
    assert result.position_on_edge_m == 5.0
    assert result.velocity_kmh == 0.0
    assert not result.crossed_edge


def test_mover_crosses_edge_on_green_light() -> None:
    edges = {EDGE_A: _edge(length_m=5.0), EDGE_B: _edge(length_m=1000.0)}
    movers = [_mover("v1", 0.0)]
    light_states = {NODE_END_A: LightState.GREEN}

    results = step_edge_occupants(movers, edges, light_states, dt_seconds=1.0, min_gap_m=3.0)

    assert len(results) == 1
    result = results[0]
    assert result.edge_id == EDGE_B
    assert result.crossed_edge
    assert result.position_on_edge_m == 5.0  # 10m advance - 5m edge length = 5m overflow


def test_mover_arrives_when_route_ends_ignoring_light() -> None:
    edges = {EDGE_A: _edge(length_m=5.0)}
    movers = [_mover("v1", 0.0, next_edge_id=None)]
    light_states = {NODE_END_A: LightState.RED}

    results = step_edge_occupants(movers, edges, light_states, dt_seconds=1.0, min_gap_m=3.0)

    assert len(results) == 1
    result = results[0]
    assert result.arrived
    assert result.position_on_edge_m == 5.0


def test_follower_queues_behind_stopped_leader() -> None:
    edges = {EDGE_A: _edge(length_m=1000.0)}
    # Leader already stopped 10m ahead of the follower; follower is close enough
    # that closing the full free-speed distance would ram it.
    movers = [
        _mover("leader", 10.0, velocity_kmh=0.0),
        _mover("follower", 5.0, velocity_kmh=0.0),
    ]

    results = step_edge_occupants(movers, edges, {}, dt_seconds=1.0, min_gap_m=3.0)
    by_key = {r.key: r for r in results}

    # Leader has nobody ahead -> free to accelerate away.
    assert by_key["leader"].position_on_edge_m == 20.0
    # Follower must not end up closer than min_gap_m to the leader's final rear position.
    follower_gap = by_key["leader"].position_on_edge_m - 4.5 - by_key["follower"].position_on_edge_m
    assert follower_gap >= 3.0 - 1e-9


def test_emergency_vehicle_ignores_red_light_and_queue() -> None:
    edges = {EDGE_A: _edge(length_m=5.0), EDGE_B: _edge(length_m=1000.0)}
    movers = [
        _mover("blocker", 5.0, velocity_kmh=0.0),
        _mover("ambulance", 0.0, is_emergency=True),
    ]
    light_states = {NODE_END_A: LightState.RED}

    results = step_edge_occupants(movers, edges, light_states, dt_seconds=1.0, min_gap_m=3.0)
    by_key = {r.key: r for r in results}

    assert by_key["blocker"].edge_id == EDGE_A
    assert by_key["blocker"].velocity_kmh == 0.0

    assert by_key["ambulance"].crossed_edge
    assert by_key["ambulance"].edge_id == EDGE_B


def test_backpressure_blocks_entry_when_next_edge_is_jammed() -> None:
    edges = {EDGE_A: _edge(length_m=5.0), EDGE_B: _edge(length_m=1000.0)}
    movers = [
        _mover("v1", 0.0, edge_id=EDGE_A, next_edge_id=EDGE_B),
        # Next edge already has a mover right at its start (no room to enter).
        _mover("blocker_on_next_edge", 1.0, edge_id=EDGE_B, next_edge_id=None),
    ]
    light_states = {NODE_END_A: LightState.GREEN}

    results = step_edge_occupants(movers, edges, light_states, dt_seconds=1.0, min_gap_m=3.0)
    by_key = {r.key: r for r in results}

    assert by_key["v1"].edge_id == EDGE_A
    assert not by_key["v1"].crossed_edge
    assert by_key["v1"].velocity_kmh == 0.0


def test_speed_factor_scales_free_speed() -> None:
    edges = {EDGE_A: _edge(length_m=1000.0, max_speed_kmh=36.0)}
    movers = [_mover("slow", 0.0, next_edge_id=None)]

    fast_mover = Mover(
        key="fast",
        current_edge_id=EDGE_A,
        position_on_edge_m=0.0,
        velocity_kmh=0.0,
        length_m=2.0,
        is_emergency=False,
        next_edge_id=None,
        speed_factor=1.5,
    )

    slow_results = step_edge_occupants(movers, edges, {}, dt_seconds=1.0, min_gap_m=3.0)
    fast_results = step_edge_occupants([fast_mover], edges, {}, dt_seconds=1.0, min_gap_m=3.0)

    assert slow_results[0].position_on_edge_m == 10.0
    assert fast_results[0].position_on_edge_m == 15.0


def test_room_ahead_allows_entry_when_next_edge_has_space() -> None:
    edges = {EDGE_A: _edge(length_m=5.0), EDGE_B: _edge(length_m=1000.0)}
    movers = [
        _mover("v1", 0.0, edge_id=EDGE_A, next_edge_id=EDGE_B),
        _mover("far_ahead", 500.0, edge_id=EDGE_B, next_edge_id=None),
    ]
    light_states = {NODE_END_A: LightState.GREEN}

    results = step_edge_occupants(movers, edges, light_states, dt_seconds=1.0, min_gap_m=3.0)
    by_key = {r.key: r for r in results}

    assert by_key["v1"].edge_id == EDGE_B
    assert by_key["v1"].crossed_edge
