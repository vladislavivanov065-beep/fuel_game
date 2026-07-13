import enum
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, model_validator


class StationUpgradeTypeSettings(BaseModel):
    """Per-upgrade-type coefficients (TECHNICAL_SPEC.md section 19): every
    upgrade has a level, cost, build time, maintenance cost, and bonuses.

    ``bonus_per_level`` is a generic attractiveness/effect coefficient whose
    exact meaning depends on the upgrade type (extra pumps, extra capacity
    liters, rating points, score weight, ...); ``revenue_per_level`` is the
    extra money generated per fuel sale at the station, where applicable.
    ``maintenance_per_level`` is tracked but not yet auto-deducted (see
    Этап 9 known limitations).
    """

    base_cost: Decimal = Field(gt=0)
    cost_per_level: Decimal = Field(ge=0)
    build_minutes: float = Field(gt=0)
    maintenance_per_level: Decimal = Field(ge=0)
    bonus_per_level: float = Field(ge=0)
    revenue_per_level: Decimal = Field(ge=0)
    min_station_level: int = Field(default=1, gt=0)


_DEFAULT_STATION_UPGRADES: dict[str, StationUpgradeTypeSettings] = {
    "pumps": StationUpgradeTypeSettings(
        base_cost=Decimal("500000"),
        cost_per_level=Decimal("250000"),
        build_minutes=10.0,
        maintenance_per_level=Decimal("2000"),
        bonus_per_level=1.0,
        revenue_per_level=Decimal("0"),
    ),
    "tanks": StationUpgradeTypeSettings(
        base_cost=Decimal("400000"),
        cost_per_level=Decimal("200000"),
        build_minutes=15.0,
        maintenance_per_level=Decimal("1000"),
        bonus_per_level=5000.0,
        revenue_per_level=Decimal("0"),
    ),
    "shop": StationUpgradeTypeSettings(
        base_cost=Decimal("300000"),
        cost_per_level=Decimal("150000"),
        build_minutes=10.0,
        maintenance_per_level=Decimal("3000"),
        bonus_per_level=0.3,
        revenue_per_level=Decimal("50"),
    ),
    "food_court": StationUpgradeTypeSettings(
        base_cost=Decimal("600000"),
        cost_per_level=Decimal("300000"),
        build_minutes=20.0,
        maintenance_per_level=Decimal("5000"),
        bonus_per_level=0.4,
        revenue_per_level=Decimal("80"),
    ),
    "car_wash": StationUpgradeTypeSettings(
        base_cost=Decimal("350000"),
        cost_per_level=Decimal("150000"),
        build_minutes=12.0,
        maintenance_per_level=Decimal("2000"),
        bonus_per_level=0.2,
        revenue_per_level=Decimal("100"),
    ),
    "rating": StationUpgradeTypeSettings(
        base_cost=Decimal("250000"),
        cost_per_level=Decimal("150000"),
        build_minutes=8.0,
        maintenance_per_level=Decimal("1000"),
        bonus_per_level=0.2,
        revenue_per_level=Decimal("0"),
    ),
    "advertising": StationUpgradeTypeSettings(
        base_cost=Decimal("200000"),
        cost_per_level=Decimal("180000"),
        build_minutes=15.0,
        maintenance_per_level=Decimal("0"),
        bonus_per_level=0.5,
        revenue_per_level=Decimal("0"),
    ),
    "parking": StationUpgradeTypeSettings(
        base_cost=Decimal("150000"),
        cost_per_level=Decimal("100000"),
        build_minutes=8.0,
        maintenance_per_level=Decimal("500"),
        bonus_per_level=0.15,
        revenue_per_level=Decimal("0"),
    ),
    "loyalty_program": StationUpgradeTypeSettings(
        base_cost=Decimal("450000"),
        cost_per_level=Decimal("250000"),
        build_minutes=15.0,
        maintenance_per_level=Decimal("2000"),
        bonus_per_level=0.5,
        revenue_per_level=Decimal("0"),
    ),
}


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

    starting_fuel_fill_ratio: float = Field(default=0.5, ge=0, le=1)
    min_retail_price_per_liter: Decimal = Field(default=Decimal("30.00"), gt=0)
    max_retail_price_per_liter: Decimal = Field(default=Decimal("100.00"), gt=0)
    price_change_cooldown_seconds: int = Field(default=30, ge=0)
    allow_selling_below_cost: bool = False
    base_demand_liters_per_tick: Decimal = Field(default=Decimal("50.00"), ge=0)
    reference_fuel_price_per_liter: Decimal = Field(default=Decimal("55.00"), gt=0)
    economic_tick_interval_seconds: int = Field(default=8, gt=0)

    base_delivery_fee: Decimal = Field(default=Decimal("2000.00"), ge=0)
    delivery_cost_per_km: Decimal = Field(default=Decimal("15.00"), ge=0)
    fuel_truck_capacity_liters: Decimal = Field(default=Decimal("16000.00"), gt=0)
    refinery_starting_stock_liters: Decimal = Field(default=Decimal("500000.00"), ge=0)
    refinery_loading_speed_liters_per_minute: float = Field(default=2000.0, gt=0)
    refinery_ai92_purchase_price: Decimal = Field(default=Decimal("42.00"), gt=0)
    refinery_ai95_purchase_price: Decimal = Field(default=Decimal("45.00"), gt=0)
    refinery_diesel_purchase_price: Decimal = Field(default=Decimal("47.00"), gt=0)

    vehicle_spawn_per_minute: float = Field(default=20.0, ge=0)
    vehicle_tank_capacity_liters: Decimal = Field(default=Decimal("50.00"), gt=0)
    vehicle_refuel_threshold_ratio: float = Field(default=0.3, ge=0, le=1)
    vehicle_max_detour_km: float = Field(default=5.0, gt=0)
    vehicle_average_service_minutes: float = Field(default=3.0, gt=0)
    station_pump_count: int = Field(default=2, gt=0)
    station_price_score_weight: float = Field(default=1.0, ge=0)
    station_distance_score_weight: float = Field(default=1.0, ge=0)
    station_queue_score_weight: float = Field(default=1.0, ge=0)
    station_rating_score_weight: float = Field(default=1.0, ge=0)
    station_random_factor_weight: float = Field(default=0.2, ge=0)
    vehicle_max_queue_length: int = Field(default=8, gt=0)
    station_rating_increase_per_sale: float = Field(default=0.01, ge=0)
    station_rating_decrease_per_stockout: float = Field(default=0.05, ge=0)

    station_upgrades: dict[str, StationUpgradeTypeSettings] = Field(
        default_factory=lambda: dict(_DEFAULT_STATION_UPGRADES)
    )
    station_upgrade_score_weight: float = Field(default=1.0, ge=0)
    station_advertising_score_weight: float = Field(default=1.0, ge=0)
    station_loyalty_score_weight: float = Field(default=1.0, ge=0)
    car_wash_visit_probability: float = Field(default=0.5, ge=0, le=1)

    @model_validator(mode="after")
    def _check_price_bounds(self) -> Self:
        if self.min_retail_price_per_liter >= self.max_retail_price_per_liter:
            raise ValueError(
                "min_retail_price_per_liter must be less than max_retail_price_per_liter"
            )
        return self
