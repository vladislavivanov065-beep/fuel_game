import math
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.financial_transaction import (
    TRANSACTION_TYPE_ANCILLARY_REVENUE,
    TRANSACTION_TYPE_FUEL_SALE,
    FinancialTransaction,
)
from app.db.models.fuel_sale import FuelSale
from app.db.models.game_player import GamePlayer
from app.db.models.game_room import GameRoom, GameStatus
from app.db.models.game_station import STATION_STATUS_ACTIVE, GameStation
from app.db.models.station_fuel import FuelType, StationFuel
from app.db.models.station_upgrade import UpgradeType
from app.db.models.traffic_light import TrafficLight
from app.db.models.vehicle import DriverType, Vehicle, VehicleStatus, VehicleType
from app.schemas.game_settings import EventModifiers, GameSettings, VehicleTypeSettings
from app.services import event_service, routing_service
from app.simulation import traffic
from app.simulation.station_upgrades import get_active_upgrade_levels
from app.simulation.traffic_lights import light_state_at

_CENTS = Decimal("0.01")
_DEFAULT_VEHICLE_TYPE_SETTINGS = VehicleTypeSettings(length_meters=4.5, speed_factor=1.0)


def _choose_vehicle_type(
    settings: GameSettings, rng: random.Random
) -> tuple[VehicleType, VehicleTypeSettings]:
    type_names = list(settings.vehicle_types.keys())
    weights = [settings.vehicle_types[name].spawn_weight for name in type_names]
    chosen_name = rng.choices(type_names, weights=weights, k=1)[0]
    return VehicleType(chosen_name), settings.vehicle_types[chosen_name]


_ATTRACTIVENESS_UPGRADE_TYPES = (
    UpgradeType.PUMPS,
    UpgradeType.TANKS,
    UpgradeType.SHOP,
    UpgradeType.FOOD_COURT,
    UpgradeType.CAR_WASH,
    UpgradeType.PARKING,
)


def _score_components_from_upgrades(
    levels: dict[UpgradeType, int], settings: GameSettings
) -> tuple[float, float, float]:
    """upgrade_score/advertising_score/loyalty_score per TECHNICAL_SPEC.md section 16.

    These three components were explicitly deferred in Этап 8 pending the
    Этап 9 upgrade system; ``levels`` holds each upgrade's *effective*
    level (0 if none/expired) at one station.
    """
    upgrade_score = sum(
        levels.get(upgrade_type, 0) * settings.station_upgrades[upgrade_type.value].bonus_per_level
        for upgrade_type in _ATTRACTIVENESS_UPGRADE_TYPES
    )
    advertising_score = (
        levels.get(UpgradeType.ADVERTISING, 0)
        * settings.station_upgrades[UpgradeType.ADVERTISING.value].bonus_per_level
    )
    loyalty_score = (
        levels.get(UpgradeType.LOYALTY_PROGRAM, 0)
        * settings.station_upgrades[UpgradeType.LOYALTY_PROGRAM.value].bonus_per_level
    )
    return upgrade_score, advertising_score, loyalty_score


@dataclass(frozen=True)
class DriverProfile:
    price_sensitivity: float
    distance_sensitivity: float
    queue_sensitivity: float
    rating_sensitivity: float


_DRIVER_PROFILES: dict[DriverType, DriverProfile] = {
    # Экономный: сильно реагирует на цену, готов ехать дальше, меньше реагирует на рейтинг.
    DriverType.ECONOMICAL: DriverProfile(1.6, 0.5, 0.7, 0.5),
    # Спешащий: выбирает ближайшую АЗС, не любит очереди, менее чувствителен к цене.
    DriverType.HURRIED: DriverProfile(0.5, 1.6, 1.4, 0.6),
    # Лояльный: предпочитает высокий рейтинг.
    DriverType.LOYAL: DriverProfile(0.7, 0.8, 0.7, 1.6),
    # Премиальный: меньше реагирует на цену.
    DriverType.PREMIUM: DriverProfile(0.4, 0.7, 0.6, 1.3),
    # Случайный: смешанные коэффициенты (сильно рандомизируется при выборке).
    DriverType.RANDOM: DriverProfile(1.0, 1.0, 1.0, 1.0),
}


def sample_driver_profile(driver_type: DriverType, rng: random.Random) -> DriverProfile:
    base = _DRIVER_PROFILES[driver_type]
    jitter = 0.3 if driver_type is DriverType.RANDOM else 0.15

    def jittered(value: float) -> float:
        return max(0.05, value * rng.uniform(1 - jitter, 1 + jitter))

    return DriverProfile(
        price_sensitivity=jittered(base.price_sensitivity),
        distance_sensitivity=jittered(base.distance_sensitivity),
        queue_sensitivity=jittered(base.queue_sensitivity),
        rating_sensitivity=jittered(base.rating_sensitivity),
    )


@dataclass(frozen=True)
class StationCandidate:
    station_id: uuid.UUID
    retail_price: Decimal
    detour_km: float
    queue_length: int
    rating: float
    upgrade_score: float = 0.0
    advertising_score: float = 0.0
    loyalty_score: float = 0.0


def compute_station_score(
    candidate: StationCandidate,
    *,
    cheapest_available_price: Decimal,
    profile: DriverProfile,
    settings: GameSettings,
    random_factor: float,
) -> float:
    """station_score per TECHNICAL_SPEC.md section 16."""
    price_score = float(cheapest_available_price) / float(candidate.retail_price)
    distance_score = 1.0 / (1.0 + candidate.detour_km)
    queue_score = 1.0 / (1.0 + max(candidate.queue_length, 0))
    rating_score = candidate.rating / 5.0

    return (
        price_score * profile.price_sensitivity * settings.station_price_score_weight
        + distance_score * profile.distance_sensitivity * settings.station_distance_score_weight
        + queue_score * profile.queue_sensitivity * settings.station_queue_score_weight
        + rating_score * profile.rating_sensitivity * settings.station_rating_score_weight
        + candidate.upgrade_score * settings.station_upgrade_score_weight
        + candidate.advertising_score * settings.station_advertising_score_weight
        + candidate.loyalty_score * settings.station_loyalty_score_weight
        + random_factor * settings.station_random_factor_weight
    )


def choose_station_index(scores: list[float], rng: random.Random) -> int:
    """Probabilistic softmax choice: probability_i = exp(score_i) / sum(exp(all_scores))."""
    max_score = max(scores)
    exp_scores = [math.exp(score - max_score) for score in scores]
    total = sum(exp_scores)
    probabilities = [value / total for value in exp_scores]

    roll = rng.random()
    cumulative = 0.0
    for index, probability in enumerate(probabilities):
        cumulative += probability
        if roll <= cumulative:
            return index
    return len(scores) - 1


def _build_vehicle_route(
    nodes: list[routing_service.GraphNode],
    edges: list[routing_service.GraphEdge],
    home_node: routing_service.GraphNode,
    destination_node: routing_service.GraphNode,
    station_node: routing_service.GraphNode | None,
) -> dict[str, Any]:
    waypoint_node_ids = [home_node.id]
    if station_node is not None:
        waypoint_node_ids.append(station_node.id)
    waypoint_node_ids.append(destination_node.id)

    route = routing_service.build_multi_stop_route(nodes, edges, waypoint_node_ids)
    positions = list(range(len(route.stop_point_indices)))
    return routing_service.serialize_multi_stop_route(route, positions)


async def _load_station_candidates(
    db: AsyncSession, game_id: uuid.UUID
) -> list[tuple[GameStation, dict[FuelType, Any], dict[UpgradeType, int]]]:
    stations = (
        (
            await db.execute(
                select(GameStation)
                .where(
                    GameStation.game_id == game_id,
                    GameStation.owner_player_id.is_not(None),
                    GameStation.status == STATION_STATUS_ACTIVE,
                )
                .options(
                    selectinload(GameStation.station_template),
                    selectinload(GameStation.fuels),
                )
            )
        )
        .scalars()
        .all()
    )
    return [
        (
            station,
            {fuel.fuel_type: fuel for fuel in station.fuels},
            await get_active_upgrade_levels(db, station.id),
        )
        for station in stations
    ]


def _event_attractiveness_bonus(
    *,
    station: GameStation,
    upgrade_levels: dict[UpgradeType, int],
    bonuses: list[event_service.AttractivenessBonus],
) -> float:
    total = 0.0
    for bonus in bonuses:
        if bonus.region is not None:
            distance_km = routing_service.haversine_km(
                station.station_template.latitude,
                station.station_template.longitude,
                bonus.region.latitude,
                bonus.region.longitude,
            )
            if distance_km > bonus.region.radius_km:
                continue
        if bonus.required_upgrade_types:
            has_required = any(
                upgrade_levels.get(UpgradeType(upgrade_type), 0) > 0
                for upgrade_type in bonus.required_upgrade_types
            )
            if not has_required:
                continue
        total += bonus.bonus
    return total


def _select_station_for_vehicle(
    *,
    stations: list[tuple[GameStation, dict[FuelType, Any], dict[UpgradeType, int]]],
    fuel_type: FuelType,
    home_lat: float,
    home_lon: float,
    dest_lat: float,
    dest_lon: float,
    profile: DriverProfile,
    settings: GameSettings,
    rng: random.Random,
    event_modifiers: EventModifiers,
    attractiveness_bonuses: list[event_service.AttractivenessBonus],
) -> GameStation | None:
    direct_km = routing_service.haversine_km(home_lat, home_lon, dest_lat, dest_lon)

    candidates: list[StationCandidate] = []
    stations_by_id: dict[uuid.UUID, GameStation] = {}
    for station, fuels_by_type, upgrade_levels in stations:
        fuel = fuels_by_type.get(fuel_type)
        if fuel is None or fuel.current_liters <= Decimal("0"):
            continue

        station_lat = station.station_template.latitude
        station_lon = station.station_template.longitude
        detour_km = (
            routing_service.haversine_km(home_lat, home_lon, station_lat, station_lon)
            + routing_service.haversine_km(station_lat, station_lon, dest_lat, dest_lon)
            - direct_km
        )
        if detour_km > settings.vehicle_max_detour_km:
            continue

        upgrade_score, advertising_score, loyalty_score = _score_components_from_upgrades(
            upgrade_levels, settings
        )
        upgrade_score += _event_attractiveness_bonus(
            station=station, upgrade_levels=upgrade_levels, bonuses=attractiveness_bonuses
        )
        candidates.append(
            StationCandidate(
                station_id=station.id,
                retail_price=fuel.retail_price,
                detour_km=max(0.0, detour_km),
                queue_length=station.queue_length,
                rating=station.rating,
                upgrade_score=upgrade_score,
                advertising_score=advertising_score,
                loyalty_score=loyalty_score,
            )
        )
        stations_by_id[station.id] = station

    if not candidates:
        return None

    event_profile = DriverProfile(
        price_sensitivity=profile.price_sensitivity * event_modifiers.price_sensitivity_multiplier,
        distance_sensitivity=profile.distance_sensitivity,
        queue_sensitivity=profile.queue_sensitivity,
        rating_sensitivity=profile.rating_sensitivity,
    )

    cheapest_price = min(candidate.retail_price for candidate in candidates)
    scores = [
        compute_station_score(
            candidate,
            cheapest_available_price=cheapest_price,
            profile=event_profile,
            settings=settings,
            random_factor=rng.uniform(0.0, 1.0),
        )
        for candidate in candidates
    ]
    chosen = candidates[choose_station_index(scores, rng)]
    return stations_by_id[chosen.station_id]


_last_spawn_check: dict[uuid.UUID, datetime] = {}
_spawn_accumulator: dict[uuid.UUID, float] = {}


async def spawn_vehicles_for_game(
    db: AsyncSession, game_id: uuid.UUID, *, rng: random.Random | None = None
) -> list[uuid.UUID]:
    """Batch-spawn new vehicles for one running game, up to max_active_vehicles.

    Called from the scheduler's batch loop (no per-vehicle background task).
    Homes/destinations are random road-graph nodes ("virtual homes" per
    TECHNICAL_SPEC.md section 15.1 — no separate Home entity is needed for
    the MVP scale of this project).
    """
    rng = rng or random.Random()

    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None or game.status != GameStatus.RUNNING:
        return []

    settings = GameSettings.model_validate(game.settings_json)
    event_modifiers, attractiveness_bonuses = await event_service.get_active_event_effects(
        db, game_id
    )

    active_count = (
        await db.execute(
            select(func.count()).select_from(Vehicle).where(Vehicle.game_id == game_id)
        )
    ).scalar_one()
    capacity = max(0, settings.max_active_vehicles - active_count)

    now = datetime.now(UTC)
    last_check = _last_spawn_check.get(game_id)
    _last_spawn_check[game_id] = now
    if last_check is None or capacity <= 0:
        return []

    effective_spawn_per_minute = (
        settings.vehicle_spawn_per_minute * event_modifiers.vehicle_spawn_multiplier
    )
    effective_refuel_threshold = (
        settings.vehicle_refuel_threshold_ratio * event_modifiers.refuel_threshold_multiplier
    )

    elapsed_minutes = (now - last_check).total_seconds() / 60.0
    _spawn_accumulator[game_id] = (
        _spawn_accumulator.get(game_id, 0.0) + effective_spawn_per_minute * elapsed_minutes
    )
    spawn_count = min(capacity, int(_spawn_accumulator[game_id]))
    if spawn_count <= 0:
        return []
    _spawn_accumulator[game_id] -= spawn_count

    nodes, edges = await routing_service.load_graph(
        db, traffic_multiplier=event_modifiers.traffic_multiplier
    )
    if len(nodes) < 2:
        return []

    stations = await _load_station_candidates(db, game_id)

    spawned_ids: list[uuid.UUID] = []
    for _ in range(spawn_count):
        home_node = rng.choice(nodes)
        destination_node = rng.choice(nodes)
        if home_node.id == destination_node.id:
            continue

        driver_type = rng.choice(list(DriverType))
        profile = sample_driver_profile(driver_type, rng)
        vehicle_type, type_settings = _choose_vehicle_type(settings, rng)
        fuel_type = (
            rng.choice(type_settings.fuel_types) if type_settings.fuel_types else FuelType.AI92
        )

        tank_capacity = settings.vehicle_tank_capacity_liters * Decimal(str(rng.uniform(0.8, 1.2)))
        fuel_ratio = rng.uniform(0.05, 0.95)
        fuel_liters = (tank_capacity * Decimal(str(fuel_ratio))).quantize(
            _CENTS, rounding=ROUND_HALF_UP
        )
        budget = (
            tank_capacity
            * settings.reference_fuel_price_per_liter
            * Decimal(str(rng.uniform(1.5, 4.0)))
        ).quantize(_CENTS, rounding=ROUND_HALF_UP)

        station: GameStation | None = None
        if type_settings.refuels and fuel_ratio < effective_refuel_threshold:
            station = _select_station_for_vehicle(
                stations=stations,
                fuel_type=fuel_type,
                home_lat=home_node.latitude,
                home_lon=home_node.longitude,
                dest_lat=destination_node.latitude,
                dest_lon=destination_node.longitude,
                profile=profile,
                settings=settings,
                rng=rng,
                event_modifiers=event_modifiers,
                attractiveness_bonuses=attractiveness_bonuses,
            )

        station_node = None
        if station is not None:
            station_node = routing_service.find_nearest_node(
                nodes, station.station_template.latitude, station.station_template.longitude
            )

        try:
            route_json = _build_vehicle_route(
                nodes, edges, home_node, destination_node, station_node
            )
        except routing_service.NoRouteFoundError:
            if station_node is None:
                continue
            try:
                route_json = _build_vehicle_route(nodes, edges, home_node, destination_node, None)
                station = None
            except routing_service.NoRouteFoundError:
                continue

        route_points = route_json["points"]
        initial_edge_id = uuid.UUID(route_points[1]["edge_id"]) if len(route_points) > 1 else None

        vehicle = Vehicle(
            game_id=game_id,
            driver_type=driver_type,
            vehicle_type=vehicle_type,
            fuel_type=fuel_type,
            home_latitude=home_node.latitude,
            home_longitude=home_node.longitude,
            destination_latitude=destination_node.latitude,
            destination_longitude=destination_node.longitude,
            route_json=route_json,
            route_progress=0.0,
            current_latitude=home_node.latitude,
            current_longitude=home_node.longitude,
            route_edge_index=1,
            current_edge_id=initial_edge_id,
            position_on_edge_m=0.0,
            velocity_kmh=0.0,
            tank_capacity_liters=tank_capacity,
            fuel_liters=fuel_liters,
            budget=budget,
            price_sensitivity=profile.price_sensitivity,
            distance_sensitivity=profile.distance_sensitivity,
            queue_sensitivity=profile.queue_sensitivity,
            rating_sensitivity=profile.rating_sensitivity,
            chosen_station_id=station.id if station is not None else None,
            started_at=now,
        )
        db.add(vehicle)
        spawned_ids.append(vehicle.id)

    if spawned_ids:
        await db.commit()
    return spawned_ids


@dataclass(frozen=True)
class VehiclePurchaseResult:
    vehicle_id: uuid.UUID
    station_id: uuid.UUID
    player_id: uuid.UUID
    fuel_type: FuelType
    liters: Decimal
    total_amount: Decimal
    ancillary_amount: Decimal = Decimal("0")


@dataclass(frozen=True)
class VehicleTickResult:
    updated_vehicle_ids: list[uuid.UUID]
    arrived_vehicle_ids: list[uuid.UUID]
    purchases: list[VehiclePurchaseResult]


def _clamp_rating(rating: float) -> float:
    return max(1.0, min(5.0, rating))


async def _complete_purchase(
    db: AsyncSession,
    vehicle: Vehicle,
    settings: GameSettings,
    rng: random.Random,
    ancillary_revenue_multiplier: float,
) -> VehiclePurchaseResult | None:
    """Vehicle purchase per TECHNICAL_SPEC.md section 17: real stock/money transfer."""
    assert vehicle.chosen_station_id is not None
    station = (
        await db.execute(
            select(GameStation).where(GameStation.id == vehicle.chosen_station_id).with_for_update()
        )
    ).scalar_one_or_none()
    if station is None:
        return None

    station.queue_length = max(0, station.queue_length - 1)

    if station.owner_player_id is None:
        return None

    station_fuel = (
        await db.execute(
            select(StationFuel)
            .where(
                StationFuel.game_station_id == station.id,
                StationFuel.fuel_type == vehicle.fuel_type,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if station_fuel is None or station_fuel.current_liters <= Decimal("0"):
        station.rating = _clamp_rating(
            station.rating - settings.station_rating_decrease_per_stockout
        )
        return None

    desired_liters = vehicle.tank_capacity_liters - vehicle.fuel_liters
    affordable_liters = (
        (vehicle.budget / station_fuel.retail_price)
        if station_fuel.retail_price > 0
        else Decimal("0")
    )
    purchasable = min(desired_liters, station_fuel.current_liters, affordable_liters)
    purchasable = purchasable.quantize(_CENTS, rounding=ROUND_HALF_UP)
    if purchasable <= Decimal("0"):
        return None

    player = (
        await db.execute(
            select(GamePlayer).where(GamePlayer.id == station.owner_player_id).with_for_update()
        )
    ).scalar_one_or_none()
    if player is None:
        return None

    total_amount = (purchasable * station_fuel.retail_price).quantize(
        _CENTS, rounding=ROUND_HALF_UP
    )
    cost_amount = (purchasable * station_fuel.average_purchase_price).quantize(
        _CENTS, rounding=ROUND_HALF_UP
    )
    profit_amount = total_amount - cost_amount

    station_fuel.current_liters -= purchasable
    vehicle.fuel_liters += purchasable
    vehicle.budget -= total_amount
    station.rating = _clamp_rating(station.rating + settings.station_rating_increase_per_sale)

    balance_before = player.balance
    balance_after = balance_before + total_amount
    player.balance = balance_after

    db.add(
        FuelSale(
            game_id=vehicle.game_id,
            station_id=station.id,
            fuel_type=vehicle.fuel_type,
            liters=purchasable,
            price_per_liter=station_fuel.retail_price,
            total_amount=total_amount,
            cost_amount=cost_amount,
            profit_amount=profit_amount,
        )
    )
    db.add(
        FinancialTransaction(
            game_id=vehicle.game_id,
            player_id=player.id,
            transaction_type=TRANSACTION_TYPE_FUEL_SALE,
            amount=total_amount,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type="vehicle_purchase",
            reference_id=vehicle.id,
        )
    )

    ancillary_amount = await _apply_ancillary_revenue(
        db, station, player, settings, rng, ancillary_revenue_multiplier
    )

    return VehiclePurchaseResult(
        vehicle_id=vehicle.id,
        station_id=station.id,
        player_id=player.id,
        fuel_type=vehicle.fuel_type,
        liters=purchasable,
        total_amount=total_amount,
        ancillary_amount=ancillary_amount,
    )


async def _apply_ancillary_revenue(
    db: AsyncSession,
    station: GameStation,
    player: GamePlayer,
    settings: GameSettings,
    rng: random.Random,
    ancillary_revenue_multiplier: float,
) -> Decimal:
    """Extra revenue from shop/food-court/car-wash upgrades (section 19.1-19.3).

    Car wash revenue is probabilistic (not every vehicle visits it); shop and
    food court revenue is earned on every fuel purchase at the station.
    """
    levels = await get_active_upgrade_levels(db, station.id)

    amount = Decimal("0")
    shop_level = levels.get(UpgradeType.SHOP, 0)
    if shop_level:
        amount += settings.station_upgrades[UpgradeType.SHOP.value].revenue_per_level * shop_level

    food_court_level = levels.get(UpgradeType.FOOD_COURT, 0)
    if food_court_level:
        amount += (
            settings.station_upgrades[UpgradeType.FOOD_COURT.value].revenue_per_level
            * food_court_level
        )

    car_wash_level = levels.get(UpgradeType.CAR_WASH, 0)
    if car_wash_level and rng.random() < settings.car_wash_visit_probability:
        amount += (
            settings.station_upgrades[UpgradeType.CAR_WASH.value].revenue_per_level * car_wash_level
        )

    amount = amount * Decimal(str(ancillary_revenue_multiplier))
    if amount <= Decimal("0"):
        return Decimal("0")

    amount = amount.quantize(_CENTS, rounding=ROUND_HALF_UP)
    balance_before = player.balance
    balance_after = balance_before + amount
    player.balance = balance_after

    db.add(
        FinancialTransaction(
            game_id=station.game_id,
            player_id=player.id,
            transaction_type=TRANSACTION_TYPE_ANCILLARY_REVENUE,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type="station_ancillary",
            reference_id=station.id,
        )
    )
    return amount


_PHYSICS_DT_SECONDS = 1.0  # matches scheduler._POLL_INTERVAL_SECONDS


async def update_vehicles_for_game(
    db: AsyncSession, game_id: uuid.UUID, *, rng: random.Random | None = None
) -> VehicleTickResult:
    """Advance every active vehicle: drive (car-following physics + traffic
    lights), queue at a chosen station, buy fuel, arrive.

    Called from the scheduler's batch loop (no background task per vehicle).
    Positions are now driven by a real per-tick physics step (Этап 14.3)
    instead of a pure function of elapsed wall-clock time — vehicles queue
    behind each other on each edge and stop at red/yellow lights (except
    emergency vehicle types, which ignore both).
    """
    rng = rng or random.Random()
    now = datetime.now(UTC)

    game = (await db.execute(select(GameRoom).where(GameRoom.id == game_id))).scalar_one_or_none()
    if game is None:
        return VehicleTickResult(updated_vehicle_ids=[], arrived_vehicle_ids=[], purchases=[])
    settings = GameSettings.model_validate(game.settings_json)
    event_modifiers, _ = await event_service.get_active_event_effects(db, game_id)

    vehicle_rows = list(
        (await db.execute(select(Vehicle).where(Vehicle.game_id == game_id))).scalars()
    )

    updated_vehicle_ids: list[uuid.UUID] = []
    arrived_vehicle_ids: list[uuid.UUID] = []
    purchases: list[VehiclePurchaseResult] = []

    driving_vehicles: list[Vehicle] = []
    for vehicle in vehicle_rows:
        if vehicle.status != VehicleStatus.REFUELING:
            driving_vehicles.append(vehicle)
            continue

        if vehicle.station_departure_at is None or now < vehicle.station_departure_at:
            continue

        purchase = await _complete_purchase(
            db, vehicle, settings, rng, event_modifiers.ancillary_revenue_multiplier
        )
        if purchase is not None:
            purchases.append(purchase)

        points = vehicle.route_json["points"]
        stop_entry = vehicle.route_json["stops"][0]
        resume_point_index = stop_entry["point_index"]
        vehicle.status = VehicleStatus.DRIVING
        vehicle.chosen_station_id = None
        vehicle.station_departure_at = None
        vehicle.route_edge_index = resume_point_index + 1
        vehicle.current_edge_id = (
            uuid.UUID(points[resume_point_index + 1]["edge_id"])
            if resume_point_index + 1 < len(points)
            else None
        )
        vehicle.position_on_edge_m = 0.0
        vehicle.velocity_kmh = 0.0
        updated_vehicle_ids.append(vehicle.id)

    if driving_vehicles:
        _, edges = await routing_service.load_graph(
            db, traffic_multiplier=event_modifiers.traffic_multiplier
        )
        edges_by_id = {
            edge.id: traffic.EdgeInfo(
                length_m=edge.distance_km * 1000.0,
                to_node_id=edge.to_node_id,
                max_speed_kmh=edge.max_speed_kmh,
                traffic_coefficient=edge.traffic_coefficient,
            )
            for edge in edges
        }
        light_rows = (await db.execute(select(TrafficLight))).scalars()
        light_states = {light.road_node_id: light_state_at(light, now) for light in light_rows}

        movers: list[traffic.Mover] = []
        for vehicle in driving_vehicles:
            if vehicle.current_edge_id is None or vehicle.current_edge_id not in edges_by_id:
                continue
            type_settings = settings.vehicle_types.get(
                vehicle.vehicle_type.value, _DEFAULT_VEHICLE_TYPE_SETTINGS
            )
            movers.append(
                traffic.Mover(
                    key=str(vehicle.id),
                    current_edge_id=vehicle.current_edge_id,
                    position_on_edge_m=vehicle.position_on_edge_m,
                    velocity_kmh=vehicle.velocity_kmh,
                    length_m=type_settings.length_meters,
                    is_emergency=type_settings.is_emergency,
                    next_edge_id=traffic.next_edge_id(
                        vehicle.route_json["points"], vehicle.route_edge_index
                    ),
                    speed_factor=type_settings.speed_factor,
                )
            )

        results_by_key = {
            result.key: result
            for result in traffic.step_edge_occupants(
                movers,
                edges_by_id,
                light_states,
                dt_seconds=_PHYSICS_DT_SECONDS,
                min_gap_m=settings.traffic_min_gap_m,
            )
        }

        for vehicle in driving_vehicles:
            result = results_by_key.get(str(vehicle.id))
            if result is None:
                continue

            if result.crossed_edge:
                vehicle.route_edge_index += 1
                vehicle.current_edge_id = result.edge_id
            vehicle.position_on_edge_m = result.position_on_edge_m
            vehicle.velocity_kmh = result.velocity_kmh

            points = vehicle.route_json["points"]
            edge_length_m = edges_by_id[result.edge_id].length_m if not result.arrived else 0.0
            if not result.arrived:
                lat, lon, heading = traffic.position_within_edge(
                    points, vehicle.route_edge_index, vehicle.position_on_edge_m, edge_length_m
                )
                vehicle.current_latitude = lat
                vehicle.current_longitude = lon
                vehicle.heading = heading
                vehicle.route_progress = traffic.route_progress(
                    points,
                    vehicle.route_edge_index,
                    vehicle.position_on_edge_m,
                    vehicle.route_json["total_distance_km"],
                )

            if result.arrived:
                vehicle.route_progress = 1.0
                arrived_vehicle_ids.append(vehicle.id)
                await db.delete(vehicle)
                continue

            if vehicle.chosen_station_id is not None:
                stop_entry = vehicle.route_json["stops"][0]
                if vehicle.route_edge_index > stop_entry["point_index"]:
                    station_point = points[stop_entry["point_index"]]
                    station = (
                        await db.execute(
                            select(GameStation)
                            .where(GameStation.id == vehicle.chosen_station_id)
                            .with_for_update()
                        )
                    ).scalar_one_or_none()
                    if station is None or station.queue_length >= settings.vehicle_max_queue_length:
                        vehicle.chosen_station_id = None
                    else:
                        upgrade_levels = await get_active_upgrade_levels(db, station.id)
                        active_pumps = (
                            settings.station_pump_count
                            + upgrade_levels.get(UpgradeType.PUMPS, 0)
                            * settings.station_upgrades[UpgradeType.PUMPS.value].bonus_per_level
                        )
                        food_court_bonus_minutes = (
                            upgrade_levels.get(UpgradeType.FOOD_COURT, 0)
                            * settings.station_upgrades[
                                UpgradeType.FOOD_COURT.value
                            ].bonus_per_level
                        )

                        waiting_time = (
                            station.queue_length * settings.vehicle_average_service_minutes
                        ) / active_pumps
                        service_minutes = (
                            settings.vehicle_average_service_minutes + food_court_bonus_minutes
                        )
                        station.queue_length += 1
                        vehicle.status = VehicleStatus.REFUELING
                        vehicle.velocity_kmh = 0.0
                        vehicle.station_departure_at = now + timedelta(
                            minutes=waiting_time + service_minutes
                        )
                        vehicle.current_latitude = station_point["latitude"]
                        vehicle.current_longitude = station_point["longitude"]

            updated_vehicle_ids.append(vehicle.id)

    await db.commit()
    return VehicleTickResult(
        updated_vehicle_ids=updated_vehicle_ids,
        arrived_vehicle_ids=arrived_vehicle_ids,
        purchases=purchases,
    )
