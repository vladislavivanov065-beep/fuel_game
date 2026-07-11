import enum
from decimal import Decimal

from pydantic import BaseModel, Field


class WinCondition(enum.StrEnum):
    NET_WORTH = "net_worth"
    REVENUE = "revenue"
    MARKET_SHARE = "market_share"
    TIME = "time"
    LAST_STANDING = "last_standing"


class Difficulty(enum.StrEnum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


class GameSettings(BaseModel):
    is_private: bool = False
    starting_balance: Decimal = Field(default=Decimal("5000000.00"), gt=0)
    free_station_price: Decimal = Field(default=Decimal("3500000.00"), gt=0)
    game_speed: float = Field(default=1.0, gt=0)
    traffic_intensity: float = Field(default=1.0, gt=0)
    event_frequency: float = Field(default=1.0, ge=0)
    purchase_price_coefficient: float = Field(default=1.0, gt=0)
    difficulty: Difficulty = Difficulty.NORMAL
    max_active_vehicles: int = Field(default=500, gt=0)
    truck_speed_kmh: float = Field(default=60.0, gt=0)
    starting_station_capacity_liters: Decimal = Field(default=Decimal("10000"), gt=0)
    trading_enabled: bool = True
    allow_join_after_start: bool = False
    duration_minutes: int = Field(default=60, gt=0)
    win_condition: WinCondition = WinCondition.TIME
