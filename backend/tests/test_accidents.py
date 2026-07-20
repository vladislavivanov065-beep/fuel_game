import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.game_room import GameRoom
from app.db.models.road_accident import AccidentSeverity, RoadAccident
from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode
from app.db.models.station_fuel import FuelType
from app.db.models.vehicle import DriverType, Vehicle, VehicleStatus
from app.db.session import async_session_factory
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.services.auth_service import register_user
from app.services.game_service import create_game, start_game
from app.simulation.accidents import (
    accident_probability_per_minute,
    edge_occupancy_ratio,
    expire_due_accidents_for_game,
    roll_accidents_for_game,
)


class _ForcedRandom(random.Random):
    """A deterministic stand-in RNG: always "rolls" the accident (random()
    returns 0.0, below any positive probability) and always returns the
    lower bound from uniform(), so tests don't depend on chance."""

    def random(self) -> float:
        return 0.0

    def uniform(self, a: float, b: float) -> float:
        return a


def test_edge_occupancy_ratio_grows_with_mover_count() -> None:
    empty = edge_occupancy_ratio(0, edge_length_m=100.0)
    light = edge_occupancy_ratio(2, edge_length_m=100.0)
    jammed = edge_occupancy_ratio(50, edge_length_m=100.0)
    assert empty == 0.0
    assert 0.0 < light < jammed
    assert jammed == 1.0  # clamped, never exceeds full capacity


def test_accident_probability_per_minute_grows_with_occupancy() -> None:
    empty_probability = accident_probability_per_minute(0.0, base_probability_per_minute=0.1)
    half_probability = accident_probability_per_minute(0.5, base_probability_per_minute=0.1)
    full_probability = accident_probability_per_minute(1.0, base_probability_per_minute=0.1)
    assert empty_probability == 0.0
    assert empty_probability < half_probability < full_probability
    assert full_probability == 0.1


async def _register(email: str) -> uuid.UUID:
    async with async_session_factory() as db:
        user, _ = await register_user(
            db, RegisterRequest(email=email, password="correcthorsebattery", display_name="Owner")
        )
        return user.id


async def _setup_running_game(name: str) -> uuid.UUID:
    creator_id = await _register(f"{name.lower()}@example.com")
    async with async_session_factory() as db:
        game = await create_game(db, creator_id, CreateGameRequest(name=name))
        game_id = game.id
    async with async_session_factory() as db:
        await start_game(db, game_id, creator_id)
    return game_id


async def _set_accident_settings(game_id: uuid.UUID, **overrides: object) -> None:
    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        settings_json = dict(game.settings_json)
        settings_json.update(overrides)
        game.settings_json = settings_json
        await db.commit()


async def _seed_edge(distance_km: float = 1.0) -> uuid.UUID:
    async with async_session_factory() as db:
        node_a = RoadNode(latitude=56.0, longitude=47.0)
        node_b = RoadNode(latitude=56.01, longitude=47.0)
        db.add_all([node_a, node_b])
        await db.flush()
        edge = RoadEdge(
            from_node_id=node_a.id,
            to_node_id=node_b.id,
            distance_km=distance_km,
            max_speed_kmh=60.0,
            road_type="local",
        )
        db.add(edge)
        await db.commit()
        await db.refresh(edge)
        return edge.id


async def _occupy_edge_with_vehicle(game_id: uuid.UUID, edge_id: uuid.UUID) -> None:
    async with async_session_factory() as db:
        vehicle = Vehicle(
            game_id=game_id,
            driver_type=DriverType.RANDOM,
            fuel_type=FuelType.AI92,
            status=VehicleStatus.DRIVING,
            home_latitude=56.0,
            home_longitude=47.0,
            destination_latitude=56.01,
            destination_longitude=47.0,
            route_json={"points": [], "stops": []},
            route_progress=0.0,
            current_latitude=56.0,
            current_longitude=47.0,
            route_edge_index=1,
            current_edge_id=edge_id,
            position_on_edge_m=0.0,
            velocity_kmh=0.0,
            tank_capacity_liters=Decimal("50"),
            fuel_liters=Decimal("40"),
            budget=Decimal("100000.00"),
            price_sensitivity=1.0,
            distance_sensitivity=1.0,
            queue_sensitivity=1.0,
            rating_sensitivity=1.0,
            started_at=datetime.now(UTC),
        )
        db.add(vehicle)
        await db.commit()


async def test_roll_accidents_for_game_never_triggers_on_an_empty_edge(
    db_session: AsyncSession,
) -> None:
    game_id = await _setup_running_game("AccidentEmpty")
    await _seed_edge()
    await _set_accident_settings(game_id, accident_base_probability_per_minute=100.0)

    async with async_session_factory() as db:
        started = await roll_accidents_for_game(db, game_id, dt_seconds=1.0, rng=_ForcedRandom())
    assert started == []

    async with async_session_factory() as db:
        rows = (await db.execute(select(RoadAccident))).scalars().all()
    assert rows == []


async def test_roll_accidents_for_game_major_closes_the_edge(db_session: AsyncSession) -> None:
    game_id = await _setup_running_game("AccidentMajor")
    edge_id = await _seed_edge()
    await _occupy_edge_with_vehicle(game_id, edge_id)
    await _set_accident_settings(
        game_id,
        accident_base_probability_per_minute=100.0,
        accident_major_probability=1.0,
    )

    async with async_session_factory() as db:
        started = await roll_accidents_for_game(db, game_id, dt_seconds=1.0, rng=_ForcedRandom())

    assert len(started) == 1
    assert started[0].severity == AccidentSeverity.MAJOR

    async with async_session_factory() as db:
        edge = await db.get(RoadEdge, edge_id)
        assert edge is not None
        assert edge.is_closed is True


async def test_roll_accidents_for_game_minor_raises_traffic_coefficient(
    db_session: AsyncSession,
) -> None:
    game_id = await _setup_running_game("AccidentMinor")
    edge_id = await _seed_edge()
    await _occupy_edge_with_vehicle(game_id, edge_id)
    await _set_accident_settings(
        game_id,
        accident_base_probability_per_minute=100.0,
        accident_major_probability=0.0,
        accident_minor_traffic_penalty=3.0,
    )

    async with async_session_factory() as db:
        started = await roll_accidents_for_game(db, game_id, dt_seconds=1.0, rng=_ForcedRandom())

    assert len(started) == 1
    assert started[0].severity == AccidentSeverity.MINOR

    async with async_session_factory() as db:
        edge = await db.get(RoadEdge, edge_id)
        assert edge is not None
        assert edge.is_closed is False
        assert edge.traffic_coefficient == 3.0


async def test_roll_accidents_for_game_skips_an_edge_with_an_active_accident(
    db_session: AsyncSession,
) -> None:
    game_id = await _setup_running_game("AccidentActive")
    edge_id = await _seed_edge()
    await _occupy_edge_with_vehicle(game_id, edge_id)
    await _set_accident_settings(game_id, accident_base_probability_per_minute=100.0)

    async with async_session_factory() as db:
        db.add(
            RoadAccident(
                game_id=game_id,
                road_edge_id=edge_id,
                severity=AccidentSeverity.MINOR,
                previous_traffic_coefficient=1.0,
                ends_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
        await db.commit()

    async with async_session_factory() as db:
        started = await roll_accidents_for_game(db, game_id, dt_seconds=1.0, rng=_ForcedRandom())
    assert started == []


async def test_expire_due_accidents_reverts_major_closure(db_session: AsyncSession) -> None:
    game_id = await _setup_running_game("AccidentExpireMajor")
    edge_id = await _seed_edge()

    async with async_session_factory() as db:
        edge = await db.get(RoadEdge, edge_id)
        edge.is_closed = True
        db.add(
            RoadAccident(
                game_id=game_id,
                road_edge_id=edge_id,
                severity=AccidentSeverity.MAJOR,
                previous_traffic_coefficient=1.0,
                ends_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        await db.commit()

    async with async_session_factory() as db:
        ended = await expire_due_accidents_for_game(db, game_id)
    assert len(ended) == 1
    assert ended[0].road_edge_id == edge_id

    async with async_session_factory() as db:
        edge = await db.get(RoadEdge, edge_id)
        assert edge is not None
        assert edge.is_closed is False

    async with async_session_factory() as db:
        rows = (await db.execute(select(RoadAccident))).scalars().all()
    assert rows == []


async def test_expire_due_accidents_restores_previous_traffic_coefficient(
    db_session: AsyncSession,
) -> None:
    game_id = await _setup_running_game("AccidentExpireMinor")
    edge_id = await _seed_edge()

    async with async_session_factory() as db:
        edge = await db.get(RoadEdge, edge_id)
        edge.traffic_coefficient = 4.5
        db.add(
            RoadAccident(
                game_id=game_id,
                road_edge_id=edge_id,
                severity=AccidentSeverity.MINOR,
                previous_traffic_coefficient=1.5,
                ends_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        await db.commit()

    async with async_session_factory() as db:
        ended = await expire_due_accidents_for_game(db, game_id)
    assert len(ended) == 1

    async with async_session_factory() as db:
        edge = await db.get(RoadEdge, edge_id)
        assert edge is not None
        assert edge.traffic_coefficient == 1.5
