import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.fuel_order import FuelOrder, FuelOrderStatus
from app.db.models.fuel_order_stop import FuelOrderStop, FuelOrderStopStatus
from app.db.models.game_station import GameStation
from app.db.models.road_edge import RoadEdge
from app.db.models.station_fuel import FuelType, StationFuel
from app.db.models.truck import Truck, TruckStatus
from app.services import routing_service


@dataclass(frozen=True)
class DeliveredStopResult:
    order_id: uuid.UUID
    player_id: uuid.UUID
    station_id: uuid.UUID
    fuel_type: FuelType
    liters: Decimal


@dataclass(frozen=True)
class TruckTickResult:
    updated_truck_ids: list[uuid.UUID]
    delivered_stops: list[DeliveredStopResult]
    completed_order_ids: list[uuid.UUID]
    rerouted_truck_ids: list[uuid.UUID]


def _interpolate_position(
    points: list[dict[str, Any]], elapsed_minutes: float
) -> tuple[float, float]:
    if elapsed_minutes <= points[0]["cumulative_minutes"]:
        return points[0]["latitude"], points[0]["longitude"]

    for previous, current in zip(points, points[1:], strict=False):
        if elapsed_minutes <= current["cumulative_minutes"]:
            t0 = previous["cumulative_minutes"]
            t1 = current["cumulative_minutes"]
            fraction = 0.0 if t1 == t0 else (elapsed_minutes - t0) / (t1 - t0)
            lat = previous["latitude"] + (current["latitude"] - previous["latitude"]) * fraction
            lon = previous["longitude"] + (current["longitude"] - previous["longitude"]) * fraction
            return lat, lon

    last = points[-1]
    return last["latitude"], last["longitude"]


async def _reroute_truck(
    db: AsyncSession,
    truck: Truck,
    current_latitude: float,
    current_longitude: float,
    remaining_stop_positions: list[int],
) -> None:
    """Rebuild the truck's route from its current position, skipping closed roads."""
    stops = (
        await db.execute(
            select(FuelOrderStop).where(FuelOrderStop.fuel_order_id == truck.fuel_order_id)
        )
    ).scalars()
    stops_by_position = {stop.position: stop for stop in stops}

    nodes, edges = await routing_service.load_graph(db)
    start_node = routing_service.find_nearest_node(nodes, current_latitude, current_longitude)

    station_ids = [stops_by_position[position].station_id for position in remaining_stop_positions]
    stations = (
        await db.execute(
            select(GameStation)
            .where(GameStation.id.in_(station_ids))
            .options(selectinload(GameStation.station_template))
        )
    ).scalars()
    stations_by_id = {station.id: station for station in stations}

    waypoint_node_ids = [start_node.id]
    for station_id in station_ids:
        station = stations_by_id[station_id]
        node = routing_service.find_nearest_node(
            nodes, station.station_template.latitude, station.station_template.longitude
        )
        waypoint_node_ids.append(node.id)

    new_route = routing_service.build_multi_stop_route(nodes, edges, waypoint_node_ids)
    route_json = routing_service.serialize_multi_stop_route(new_route, remaining_stop_positions)

    truck.route_json = route_json
    truck.started_at = datetime.now(UTC)
    truck.route_progress = 0.0
    truck.current_latitude = current_latitude
    truck.current_longitude = current_longitude


async def update_trucks_for_game(db: AsyncSession, game_id: uuid.UUID) -> TruckTickResult:
    """Advance every en-route truck by elapsed time, deliver, and reroute around closures.

    Called from the scheduler's batch loop (not a task per truck), matching
    the project's rule against a background task per entity. Truck positions
    are derived from elapsed wall-clock time against a precomputed route, so
    the client only needs a periodic correction, not a stream of coordinates.
    """
    now = datetime.now(UTC)
    trucks = (
        await db.execute(
            select(Truck).where(Truck.game_id == game_id, Truck.status == TruckStatus.EN_ROUTE)
        )
    ).scalars()

    updated_truck_ids: list[uuid.UUID] = []
    delivered_stops: list[DeliveredStopResult] = []
    completed_order_ids: list[uuid.UUID] = []
    rerouted_truck_ids: list[uuid.UUID] = []

    for truck in trucks:
        elapsed_minutes = (now - truck.started_at).total_seconds() / 60.0
        points = truck.route_json["points"]

        upcoming_edge_ids = [
            uuid.UUID(point["edge_id"])
            for point in points
            if point["edge_id"] is not None and point["cumulative_minutes"] > elapsed_minutes
        ]
        if upcoming_edge_ids:
            closed_ahead = (
                await db.execute(
                    select(RoadEdge.id).where(
                        RoadEdge.id.in_(upcoming_edge_ids), RoadEdge.is_closed.is_(True)
                    )
                )
            ).first()
            if closed_ahead is not None:
                current_lat, current_lon = _interpolate_position(points, elapsed_minutes)
                remaining_positions = sorted(
                    {
                        stop_entry["position"]
                        for stop_entry in truck.route_json["stops"]
                        if points[stop_entry["point_index"]]["cumulative_minutes"] > elapsed_minutes
                    }
                )
                if remaining_positions:
                    try:
                        await _reroute_truck(
                            db, truck, current_lat, current_lon, remaining_positions
                        )
                        rerouted_truck_ids.append(truck.id)
                        updated_truck_ids.append(truck.id)
                        continue
                    except (routing_service.EmptyGraphError, routing_service.NoRouteFoundError):
                        pass

        total_minutes = truck.route_json["total_travel_time_minutes"]
        lat, lon = _interpolate_position(points, elapsed_minutes)
        progress = (
            1.0 if total_minutes <= 0 else min(1.0, max(0.0, elapsed_minutes / total_minutes))
        )
        truck.current_latitude = lat
        truck.current_longitude = lon
        truck.route_progress = progress
        updated_truck_ids.append(truck.id)

        order = await db.get(FuelOrder, truck.fuel_order_id)
        if order is None:
            continue

        stops = (
            await db.execute(
                select(FuelOrderStop)
                .where(FuelOrderStop.fuel_order_id == truck.fuel_order_id)
                .with_for_update()
            )
        ).scalars()
        stops_by_position: dict[int, list[FuelOrderStop]] = defaultdict(list)
        stop_list = list(stops)
        for stop in stop_list:
            stops_by_position[stop.position].append(stop)

        for stop_entry in truck.route_json["stops"]:
            point = points[stop_entry["point_index"]]
            if elapsed_minutes < point["cumulative_minutes"]:
                continue
            for stop in stops_by_position.get(stop_entry["position"], []):
                if stop.status != FuelOrderStopStatus.PENDING:
                    continue
                station_fuel = (
                    await db.execute(
                        select(StationFuel)
                        .where(
                            StationFuel.game_station_id == stop.station_id,
                            StationFuel.fuel_type == stop.fuel_type,
                        )
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if station_fuel is None:
                    stop.status = FuelOrderStopStatus.FAILED
                    continue

                station_fuel.current_liters += stop.liters
                station_fuel.reserved_liters -= stop.liters
                stop.delivered_liters = stop.liters
                stop.status = FuelOrderStopStatus.DELIVERED
                delivered_stops.append(
                    DeliveredStopResult(
                        order_id=order.id,
                        player_id=order.player_id,
                        station_id=stop.station_id,
                        fuel_type=stop.fuel_type,
                        liters=stop.liters,
                    )
                )

        if progress >= 1.0 and all(
            stop.status != FuelOrderStopStatus.PENDING for stop in stop_list
        ):
            truck.status = TruckStatus.DELIVERED
            order.status = FuelOrderStatus.DELIVERED
            order.completed_at = now
            completed_order_ids.append(order.id)

    await db.commit()
    return TruckTickResult(
        updated_truck_ids=updated_truck_ids,
        delivered_stops=delivered_stops,
        completed_order_ids=completed_order_ids,
        rerouted_truck_ids=rerouted_truck_ids,
    )
