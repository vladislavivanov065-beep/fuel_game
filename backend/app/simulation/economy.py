import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import bindparam, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.financial_transaction import TRANSACTION_TYPE_FUEL_SALE, FinancialTransaction
from app.db.models.fuel_sale import FuelSale
from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom, GameStatus
from app.db.models.game_station import GameStation
from app.db.models.station_fuel import StationFuel
from app.schemas.game_settings import GameSettings

_MIN_PRICE_FACTOR = 0.5
_MAX_PRICE_FACTOR = 1.5
_CENTS = Decimal("0.01")


@dataclass(frozen=True)
class FuelSaleResult:
    liters_sold: Decimal
    total_amount: Decimal
    cost_amount: Decimal
    profit_amount: Decimal


def compute_fuel_sale(
    *,
    retail_price: Decimal,
    average_purchase_price: Decimal,
    current_liters: Decimal,
    rating: float,
    queue_length: int,
    room_settings: GameSettings,
) -> FuelSaleResult:
    """Aggregate, formula-based demand for one station-fuel per economic tick.

    No individual vehicles are simulated here (see Этап 8); this is the
    aggregated-demand model called for by TECHNICAL_SPEC.md section 45.
    """
    price_factor = float(room_settings.reference_fuel_price_per_liter) / float(retail_price)
    price_factor = max(_MIN_PRICE_FACTOR, min(price_factor, _MAX_PRICE_FACTOR))

    rating_factor = max(0.0, min(rating / 5.0, 1.0))
    queue_factor = 1.0 / (1.0 + max(queue_length, 0))

    demand_multiplier = (
        price_factor * rating_factor * queue_factor * room_settings.traffic_intensity
    )

    desired_liters = room_settings.base_demand_liters_per_tick * Decimal(str(demand_multiplier))
    liters_sold = max(Decimal("0"), min(desired_liters, current_liters))

    total_amount = (liters_sold * retail_price).quantize(_CENTS, rounding=ROUND_HALF_UP)
    cost_amount = (liters_sold * average_purchase_price).quantize(_CENTS, rounding=ROUND_HALF_UP)
    profit_amount = total_amount - cost_amount

    return FuelSaleResult(
        liters_sold=liters_sold,
        total_amount=total_amount,
        cost_amount=cost_amount,
        profit_amount=profit_amount,
    )


class GameNotFoundError(Exception):
    pass


class GameNotRunningError(Exception):
    pass


@dataclass(frozen=True)
class StationSaleResult:
    station_id: uuid.UUID
    fuel_type: str
    liters_sold: Decimal
    total_amount: Decimal
    profit_amount: Decimal


@dataclass(frozen=True)
class PlayerRevenueResult:
    player_id: uuid.UUID
    revenue: Decimal
    balance_before: Decimal
    balance_after: Decimal


@dataclass(frozen=True)
class EconomicTickResult:
    game_id: uuid.UUID
    station_sales: list[StationSaleResult]
    player_revenues: list[PlayerRevenueResult]


async def run_economic_tick_for_game(db: AsyncSession, game_id: uuid.UUID) -> EconomicTickResult:
    """Run one aggregated-demand economic tick for a single running game.

    Batch-processes every owned station-fuel in the game in a single
    transaction: computes sales, bulk-updates stock, records FuelSale rows,
    credits sellers' balances, and writes one FinancialTransaction per player.
    WebSocket broadcast is intentionally left to the caller (see CLAUDE.md:
    events are sent only after a successful commit, from the API/scheduler
    layer, not from inside service/simulation functions).
    """
    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError
    if game.status != GameStatus.RUNNING:
        raise GameNotRunningError

    room_settings = GameSettings.model_validate(game.settings_json)

    stations = (
        (
            await db.execute(
                select(GameStation)
                .where(GameStation.game_id == game_id, GameStation.owner_player_id.is_not(None))
                .options(selectinload(GameStation.fuels))
            )
        )
        .scalars()
        .all()
    )

    station_sales: list[StationSaleResult] = []
    fuel_updates: list[dict[str, uuid.UUID | Decimal]] = []
    sale_rows: list[FuelSale] = []
    player_revenue: dict[uuid.UUID, Decimal] = defaultdict(lambda: Decimal("0"))

    for station in stations:
        owner_player_id = station.owner_player_id
        assert owner_player_id is not None
        for fuel in station.fuels:
            sale = compute_fuel_sale(
                retail_price=fuel.retail_price,
                average_purchase_price=fuel.average_purchase_price,
                current_liters=fuel.current_liters,
                rating=station.rating,
                queue_length=station.queue_length,
                room_settings=room_settings,
            )
            if sale.liters_sold <= Decimal("0"):
                continue

            fuel_updates.append(
                {"fuel_id": fuel.id, "new_liters": fuel.current_liters - sale.liters_sold}
            )
            sale_rows.append(
                FuelSale(
                    game_id=game_id,
                    station_id=station.id,
                    fuel_type=fuel.fuel_type,
                    liters=sale.liters_sold,
                    price_per_liter=fuel.retail_price,
                    total_amount=sale.total_amount,
                    cost_amount=sale.cost_amount,
                    profit_amount=sale.profit_amount,
                )
            )
            station_sales.append(
                StationSaleResult(
                    station_id=station.id,
                    fuel_type=fuel.fuel_type.value,
                    liters_sold=sale.liters_sold,
                    total_amount=sale.total_amount,
                    profit_amount=sale.profit_amount,
                )
            )
            player_revenue[owner_player_id] += sale.total_amount

    if not fuel_updates:
        return EconomicTickResult(game_id=game_id, station_sales=[], player_revenues=[])

    await db.execute(
        update(StationFuel)
        .where(StationFuel.id == bindparam("fuel_id"))
        .values(current_liters=bindparam("new_liters"))
        .execution_options(synchronize_session=False, dml_strategy="core_only"),
        fuel_updates,
    )
    db.add_all(sale_rows)

    players = (
        (await db.execute(select(GamePlayer).where(GamePlayer.id.in_(player_revenue.keys()))))
        .scalars()
        .all()
    )

    player_revenues: list[PlayerRevenueResult] = []
    transactions: list[FinancialTransaction] = []
    for player in players:
        revenue = player_revenue[player.id]
        balance_before = player.balance
        balance_after = balance_before + revenue
        player.balance = balance_after
        transactions.append(
            FinancialTransaction(
                game_id=game_id,
                player_id=player.id,
                transaction_type=TRANSACTION_TYPE_FUEL_SALE,
                amount=revenue,
                balance_before=balance_before,
                balance_after=balance_after,
                reference_type="economic_tick",
            )
        )
        player_revenues.append(
            PlayerRevenueResult(
                player_id=player.id,
                revenue=revenue,
                balance_before=balance_before,
                balance_after=balance_after,
            )
        )
    db.add_all(transactions)

    await db.commit()

    return EconomicTickResult(
        game_id=game_id, station_sales=station_sales, player_revenues=player_revenues
    )
