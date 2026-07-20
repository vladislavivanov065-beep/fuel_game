import uuid
from datetime import UTC, datetime

from app.db.models.traffic_light import TrafficLight
from app.simulation.traffic_lights import LightState, light_state_at


def _light(offset_seconds: float = 0.0) -> TrafficLight:
    return TrafficLight(
        id=uuid.uuid4(),
        road_node_id=uuid.uuid4(),
        red_seconds=20.0,
        yellow_seconds=3.0,
        green_seconds=25.0,
        offset_seconds=offset_seconds,
    )


def _at(epoch_seconds: float) -> datetime:
    return datetime.fromtimestamp(epoch_seconds, tz=UTC)


def test_light_state_at_is_red_at_cycle_start() -> None:
    light = _light()
    assert light_state_at(light, _at(0.0)) == LightState.RED
    assert light_state_at(light, _at(19.9)) == LightState.RED


def test_light_state_at_is_yellow_after_red() -> None:
    light = _light()
    assert light_state_at(light, _at(20.0)) == LightState.YELLOW
    assert light_state_at(light, _at(22.9)) == LightState.YELLOW


def test_light_state_at_is_green_after_yellow() -> None:
    light = _light()
    assert light_state_at(light, _at(23.0)) == LightState.GREEN
    assert light_state_at(light, _at(47.9)) == LightState.GREEN


def test_light_state_at_wraps_around_to_red_next_cycle() -> None:
    light = _light()
    cycle_length = 20.0 + 3.0 + 25.0
    assert light_state_at(light, _at(cycle_length)) == LightState.RED
    assert light_state_at(light, _at(cycle_length + 10.0)) == LightState.RED


def test_light_state_at_offset_shifts_the_phase() -> None:
    unshifted = _light(offset_seconds=0.0)
    shifted = _light(offset_seconds=20.0)
    assert light_state_at(unshifted, _at(0.0)) == LightState.RED
    assert light_state_at(shifted, _at(0.0)) == LightState.YELLOW
