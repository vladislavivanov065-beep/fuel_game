import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.fuel_order import FuelOrder, FuelOrderStatus
from app.db.models.fuel_order_stop import FuelOrderStop, FuelOrderStopStatus
from app.db.models.game_room import GameRoom
from app.db.models.game_station import GameStation
from app.db.models.station_fuel import FuelType, StationFuel
from app.db.models.traffic_light import TrafficLight
from app.db.models.truck import Truck, TruckStatus
from app.schemas.game_settings import GameSettings
from app.services import event_service, routing_service
from app.simulation import traffic
from app.simulation.traffic_lights import light_state_at

_PHYSICS_DT_SECONDS = 1.0  # matches scheduler._POLL_INTERVAL_SECONDS
_TRUCK_LENGTH_M = 10.0


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


async def _reroute_truck(
    db: AsyncSession,
    truck: Truck,
    current_latitude: float,
    current_longitude: float,
    remaining_stop_positions: list[int],
    traffic_multiplier: float,
) -> None:
    """Rebuild the truck's route from its current position, skipping closed roads."""
    stops = (
        await db.execute(
            select(FuelOrderStop).where(FuelOrderStop.fuel_order_id == truck.fuel_order_id)
        )
    ).scalars()
    stops_by_position = {stop.position: stop for stop in stops}

    nodes, edges = await routing_service.load_graph(db, traffic_multiplier=traffic_multiplier)
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

    new_points = route_json["points"]
    truck.route_json = route_json
    truck.route_progress = 0.0
    truck.current_latitude = current_latitude
    truck.current_longitude = current_longitude
    truck.route_edge_index = 1
    truck.current_edge_id = uuid.UUID(new_points[1]["edge_id"]) if len(new_points) > 1 else None
    truck.position_on_edge_m = 0.0
    truck.velocity_kmh = 0.0


async def update_trucks_for_game(db: AsyncSession, game_id: uuid.UUID) -> TruckTickResult:
    """Advance every en-route truck by elapsed time, deliver, and reroute around closures.

    Called from the scheduler's batch loop (not a task per truck), matching
    the project's rule against a background task per entity. Truck positions
    are derived from elapsed wall-clock time against a precomputed route, so
    the client only needs a periodic correction, not a stream of coordinates.
    """
    now = datetime.now(UTC)
    game_room = await db.get(GameRoom, game_id)
    settings = (
        GameSettings.model_validate(game_room.settings_json)
        if game_room is not None
        else GameSettings()
    )
    event_modifiers, _ = await event_service.get_active_event_effects(db, game_id)
    trucks = list(
        (
            await db.execute(
                select(Truck).where(Truck.game_id == game_id, Truck.status == TruckStatus.EN_ROUTE)
            )
        ).scalars()
    )

    updated_truck_ids: list[uuid.UUID] = []
    delivered_stops: list[DeliveredStopResult] = []
    completed_order_ids: list[uuid.UUID] = []
    rerouted_truck_ids: list[uuid.UUID] = []

    remaining_trucks: list[Truck] = []
    for truck in trucks:
        points = truck.route_json["points"]

        upcoming_edge_ids = [
            uuid.UUID(point["edge_id"])
            for point in points[truck.route_edge_index :]
            if point["edge_id"] is not None
        ]
        closed_ahead = False
        if upcoming_edge_ids:
            nodes, edges = await routing_service.load_graph(db)
            closed_edge_ids = {edge.id for edge in edges if edge.is_closed}
            closed_ahead = any(edge_id in closed_edge_ids for edge_id in upcoming_edge_ids)

        if closed_ahead:
            current_lat, current_lon, _heading = traffic.position_within_edge(
                points,
                truck.route_edge_index,
                truck.position_on_edge_m,
                (
                    points[truck.route_edge_index]["cumulative_km"]
                    - points[truck.route_edge_index - 1]["cumulative_km"]
                )
                * 1000.0,
            )
            distance_traveled_km = (
                float(points[truck.route_edge_index - 1]["cumulative_km"])
                + truck.position_on_edge_m / 1000.0
            )
            remaining_positions = sorted(
                {
                    stop_entry["position"]
                    for stop_entry in truck.route_json["stops"]
                    if distance_traveled_km < points[stop_entry["point_index"]]["cumulative_km"]
                }
            )
            if remaining_positions:
                try:
                    await _reroute_truck(
                        db,
                        truck,
                        current_lat,
                        current_lon,
                        remaining_positions,
                        event_modifiers.traffic_multiplier,
                    )
                    rerouted_truck_ids.append(truck.id)
                    updated_truck_ids.append(truck.id)
                    continue
                except (routing_service.EmptyGraphError, routing_service.NoRouteFoundError):
                    pass

        remaining_trucks.append(truck)

    if remaining_trucks:
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
        for truck in remaining_trucks:
            if truck.current_edge_id is None or truck.current_edge_id not in edges_by_id:
                continue
            movers.append(
                traffic.Mover(
                    key=str(truck.id),
                    current_edge_id=truck.current_edge_id,
                    position_on_edge_m=truck.position_on_edge_m,
                    velocity_kmh=truck.velocity_kmh,
                    length_m=_TRUCK_LENGTH_M,
                    is_emergency=False,
                    next_edge_id=traffic.next_edge_id(
                        truck.route_json["points"], truck.route_edge_index
                    ),
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

        for truck in remaining_trucks:
            result = results_by_key.get(str(truck.id))
            if result is None:
                continue

            if result.crossed_edge:
                truck.route_edge_index += 1
                truck.current_edge_id = result.edge_id
            truck.position_on_edge_m = result.position_on_edge_m
            truck.velocity_kmh = result.velocity_kmh

            points = truck.route_json["points"]
            if not result.arrived:
                edge_length_m = edges_by_id[result.edge_id].length_m
                lat, lon, heading = traffic.position_within_edge(
                    points, truck.route_edge_index, truck.position_on_edge_m, edge_length_m
                )
                truck.current_latitude = lat
                truck.current_longitude = lon
                truck.heading = heading
                truck.route_progress = traffic.route_progress(
                    points,
                    truck.route_edge_index,
                    truck.position_on_edge_m,
                    truck.route_json["total_distance_km"],
                )
            else:
                truck.route_progress = 1.0

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

            # Distance-based (not route_edge_index-based) reached-check: a stop
            # can coincide with the truck's final arrival point, where
            # route_edge_index never advances past it (arrival has no "next
            # edge" to cross into), so an index comparison alone would never
            # fire for that last stop.
            distance_traveled_km = (
                float(points[truck.route_edge_index - 1]["cumulative_km"])
                + truck.position_on_edge_m / 1000.0
            )
            for stop_entry in truck.route_json["stops"]:
                if distance_traveled_km < points[stop_entry["point_index"]]["cumulative_km"]:
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

            if result.arrived and all(
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
