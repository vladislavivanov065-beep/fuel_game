import enum
from datetime import datetime

from app.db.models.traffic_light import TrafficLight


class LightState(enum.StrEnum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"


def light_state_at(light: TrafficLight, now: datetime) -> LightState:
    """Pure function of wall-clock time — no DB writes needed per tick, same
    principle already used for vehicle/truck route position (Этап 7/8).
    """
    cycle_length = light.red_seconds + light.yellow_seconds + light.green_seconds
    if cycle_length <= 0:
        return LightState.GREEN

    phase = (now.timestamp() + light.offset_seconds) % cycle_length
    if phase < light.red_seconds:
        return LightState.RED
    if phase < light.red_seconds + light.yellow_seconds:
        return LightState.YELLOW
    return LightState.GREEN
