import copy
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.game_event import EventStatus, EventType, GameEvent
from app.db.models.game_room import GameRoom
from app.db.models.game_station import STATION_STATUS_ACTIVE, STATION_STATUS_INACTIVE, GameStation
from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode
from app.db.models.station_template import StationTemplate
from app.db.session import async_session_factory
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.services.auth_service import register_user
from app.services.game_service import create_game, start_game
from app.services.station_service import list_game_stations, purchase_station
from app.simulation.events import expire_due_events_for_game, roll_random_event_for_game


async def _register(email: str) -> uuid.UUID:
    async with async_session_factory() as db:
        user, _ = await register_user(
            db, RegisterRequest(email=email, password="correcthorsebattery", display_name="Owner")
        )
        return user.id


async def _setup_owned_station(name: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with async_session_factory() as db:
        db.add(
            StationTemplate(
                name=f"{name} Station",
                latitude=56.0,
                longitude=47.0,
                base_price="2000000.00",
                metadata_json={},
            )
        )
        await db.commit()

    creator_id = await _register(f"{name.lower()}@example.com")
    async with async_session_factory() as db:
        game = await create_game(db, creator_id, CreateGameRequest(name=name))
        game_id = game.id
    async with async_session_factory() as db:
        await start_game(db, game_id, creator_id)
    async with async_session_factory() as db:
        stations = await list_game_stations(db, game_id)
        station_id = stations[0].id
    async with async_session_factory() as db:
        await purchase_station(db, game_id, station_id, creator_id)

    return game_id, station_id


async def test_roll_random_event_creates_event_when_probability_forces_it(
    db_session: AsyncSession,
) -> None:
    game_id, _station_id = await _setup_owned_station("RollForced")

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        assert game is not None
        settings_json = copy.deepcopy(game.settings_json)
        settings_json["event_frequency"] = 1000.0
        game.settings_json = settings_json
        await db.commit()

    async with async_session_factory() as db:
        event = await roll_random_event_for_game(db, game_id, rng=random.Random(1))

    assert event is not None
    assert event.status == EventStatus.ACTIVE


async def test_roll_random_event_skips_while_another_event_is_active(
    db_session: AsyncSession,
) -> None:
    game_id, _station_id = await _setup_owned_station("RollSkipActive")

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        assert game is not None
        settings_json = copy.deepcopy(game.settings_json)
        settings_json["event_frequency"] = 1000.0
        game.settings_json = settings_json
        await db.commit()

    async with async_session_factory() as db:
        db.add(
            GameEvent(
                game_id=game_id,
                event_type=EventType.STORM,
                status=EventStatus.ACTIVE,
                region_json=None,
                modifiers_json={"traffic_multiplier": 1.3},
                started_at=datetime.now(UTC),
                ends_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
        await db.commit()

    async with async_session_factory() as db:
        event = await roll_random_event_for_game(db, game_id, rng=random.Random(1))

    assert event is None


async def test_roll_random_event_respects_min_interval_after_last_event_ended(
    db_session: AsyncSession,
) -> None:
    game_id, _station_id = await _setup_owned_station("RollCooldown")

    async with async_session_factory() as db:
        game = await db.get(GameRoom, game_id)
        assert game is not None
        settings_json = copy.deepcopy(game.settings_json)
        settings_json["event_frequency"] = 1000.0
        settings_json["event_min_interval_seconds"] = 3600
        game.settings_json = settings_json
        await db.commit()

    async with async_session_factory() as db:
        db.add(
            GameEvent(
                game_id=game_id,
                event_type=EventType.STORM,
                status=EventStatus.EXPIRED,
                region_json=None,
                modifiers_json={"traffic_multiplier": 1.3},
                started_at=datetime.now(UTC) - timedelta(minutes=10),
                ends_at=datetime.now(UTC) - timedelta(minutes=5),
            )
        )
        await db.commit()

    async with async_session_factory() as db:
        event = await roll_random_event_for_game(db, game_id, rng=random.Random(1))

    assert event is None


async def test_expire_due_events_reopens_road_and_reactivates_station(
    db_session: AsyncSession,
) -> None:
    game_id, station_id = await _setup_owned_station("ExpireRevert")

    async with async_session_factory() as db:
        node_a = RoadNode(latitude=56.0, longitude=47.0)
        node_b = RoadNode(latitude=56.01, longitude=47.01)
        db.add_all([node_a, node_b])
        await db.flush()
        edge = RoadEdge(
            from_node_id=node_a.id,
            to_node_id=node_b.id,
            distance_km=5.0,
            max_speed_kmh=60.0,
            road_type="local",
            is_closed=True,
        )
        db.add(edge)
        await db.commit()
        edge_id = edge.id

        station = await db.get(GameStation, station_id)
        assert station is not None
        station.status = STATION_STATUS_INACTIVE
        await db.commit()

        event = GameEvent(
            game_id=game_id,
            event_type=EventType.ROAD_WORKS,
            status=EventStatus.ACTIVE,
            region_json=None,
            modifiers_json={
                "closed_edge_ids": [str(edge_id)],
                "fined_station_ids": [str(station_id)],
            },
            started_at=datetime.now(UTC) - timedelta(minutes=10),
            ends_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        db.add(event)
        await db.commit()
        event_id = event.id

    async with async_session_factory() as db:
        expired_ids = await expire_due_events_for_game(db, game_id)

    assert event_id in expired_ids

    async with async_session_factory() as db:
        event = await db.get(GameEvent, event_id)
        assert event is not None
        assert event.status == EventStatus.EXPIRED

        edge = await db.get(RoadEdge, edge_id)
        assert edge is not None
        assert edge.is_closed is False

        station = await db.get(GameStation, station_id)
        assert station is not None
        assert station.status == STATION_STATUS_ACTIVE
