from decimal import Decimal

from app.schemas.game_settings import GameSettings
from app.simulation.economy import compute_fuel_sale

_SETTINGS = GameSettings(
    base_demand_liters_per_tick=Decimal("100.00"),
    reference_fuel_price_per_liter=Decimal("50.00"),
    traffic_intensity=1.0,
)


def test_baseline_sale_matches_base_demand() -> None:
    result = compute_fuel_sale(
        retail_price=Decimal("50.00"),
        average_purchase_price=Decimal("0"),
        current_liters=Decimal("10000"),
        rating=5.0,
        queue_length=0,
        room_settings=_SETTINGS,
    )

    assert result.liters_sold == Decimal("100.00")
    assert result.total_amount == Decimal("5000.00")
    assert result.cost_amount == Decimal("0.00")
    assert result.profit_amount == Decimal("5000.00")


def test_cheaper_price_increases_demand_up_to_cap() -> None:
    cheap = compute_fuel_sale(
        retail_price=Decimal("25.00"),
        average_purchase_price=Decimal("0"),
        current_liters=Decimal("10000"),
        rating=5.0,
        queue_length=0,
        room_settings=_SETTINGS,
    )

    assert cheap.liters_sold == Decimal("150.00")


def test_expensive_price_decreases_demand_to_floor() -> None:
    expensive = compute_fuel_sale(
        retail_price=Decimal("500.00"),
        average_purchase_price=Decimal("0"),
        current_liters=Decimal("10000"),
        rating=5.0,
        queue_length=0,
        room_settings=_SETTINGS,
    )

    assert expensive.liters_sold == Decimal("50.00")


def test_low_rating_reduces_demand() -> None:
    result = compute_fuel_sale(
        retail_price=Decimal("50.00"),
        average_purchase_price=Decimal("0"),
        current_liters=Decimal("10000"),
        rating=2.5,
        queue_length=0,
        room_settings=_SETTINGS,
    )

    assert result.liters_sold == Decimal("50.00")


def test_queue_reduces_demand() -> None:
    result = compute_fuel_sale(
        retail_price=Decimal("50.00"),
        average_purchase_price=Decimal("0"),
        current_liters=Decimal("10000"),
        rating=5.0,
        queue_length=3,
        room_settings=_SETTINGS,
    )

    assert result.liters_sold == Decimal("25.00")


def test_sale_is_capped_by_available_stock() -> None:
    result = compute_fuel_sale(
        retail_price=Decimal("50.00"),
        average_purchase_price=Decimal("0"),
        current_liters=Decimal("10.00"),
        rating=5.0,
        queue_length=0,
        room_settings=_SETTINGS,
    )

    assert result.liters_sold == Decimal("10.00")
    assert result.total_amount == Decimal("500.00")


def test_no_stock_produces_zero_sale() -> None:
    result = compute_fuel_sale(
        retail_price=Decimal("50.00"),
        average_purchase_price=Decimal("0"),
        current_liters=Decimal("0"),
        rating=5.0,
        queue_length=0,
        room_settings=_SETTINGS,
    )

    assert result.liters_sold == Decimal("0")
    assert result.total_amount == Decimal("0.00")
    assert result.profit_amount == Decimal("0.00")


def test_profit_accounts_for_purchase_cost() -> None:
    result = compute_fuel_sale(
        retail_price=Decimal("50.00"),
        average_purchase_price=Decimal("30.00"),
        current_liters=Decimal("10000"),
        rating=5.0,
        queue_length=0,
        room_settings=_SETTINGS,
    )

    assert result.total_amount == Decimal("5000.00")
    assert result.cost_amount == Decimal("3000.00")
    assert result.profit_amount == Decimal("2000.00")
