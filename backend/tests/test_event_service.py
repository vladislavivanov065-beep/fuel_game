import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.financial_transaction import TRANSACTION_TYPE_EVENT_FINE, FinancialTransaction
from app.db.models.game_event import EventStatus, EventType, GameEvent
from app.db.models.game_player import GamePlayer
from app.db.models.game_station import STATION_STATUS_ACTIVE, STATION_STATUS_INACTIVE, GameStation
from app.db.models.refinery import Refinery
from app.db.models.refinery_fuel import RefineryFuel
from app.db.models.road_edge import RoadEdge
from app.db.models.road_node import RoadNode
from app.db.models.station_fuel import FuelType
from app.db.models.station_template import StationTemplate
from app.db.models.station_upgrade import StationUpgrade, UpgradeStatus, UpgradeType
from app.db.session import async_session_factory
from app.schemas.auth import RegisterRequest
from app.schemas.game import CreateGameRequest
from app.services.auth_service import register_user
from app.services.event_service import (
    GameNotRunningError,
    NotAGameMemberError,
    NotGameAdminError,
    Region,
    get_active_event_effects,
    list_attractiveness_bonuses,
    list_event_history,
    trigger_event,
)
from app.services.game_service import create_game, join_game, start_game
from app.services.station_service import list_game_stations, purchase_station
from app.services.station_upgrade_service import purchase_upgrade


async def _register(email: str) -> uuid.UUID:
    async with async_session_factory() as db:
        user, _ = await register_user(
            db, RegisterRequest(email=email, password="correcthorsebattery", display_name="Owner")
        )
        return user.id


async def _setup_owned_station(name: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Returns (game_id, station_id, owner_user_id)."""
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

    return game_id, station_id, creator_id


async def test_trigger_event_requires_admin(db_session: AsyncSession) -> None:
    async with async_session_factory() as db:
        db.add(
            StationTemplate(
                name="EvtNotAdmin Station",
                latitude=56.0,
                longitude=47.0,
                base_price="2000000.00",
                metadata_json={},
            )
        )
        await db.commit()

    creator_id = await _register("evtnotadmin_creator@example.com")
    other_id = await _register("evtnotadmin_other@example.com")

    async with async_session_factory() as db:
        game = await create_game(db, creator_id, CreateGameRequest(name="EvtNotAdmin"))
        game_id = game.id
        invite_code = game.invite_code

    async with async_session_factory() as db:
        await join_game(db, game_id, other_id, invite_code)
    async with async_session_factory() as db:
        await start_game(db, game_id, creator_id)

    async with async_session_factory() as db:
        try:
            await trigger_event(db, game_id, other_id, EventType.STORM)
            raise AssertionError("expected NotGameAdminError")
        except NotGameAdminError:
            pass


async def test_trigger_event_requires_membership(db_session: AsyncSession) -> None:
    game_id, _station_id, _owner_id = await _setup_owned_station("EvtNoMember")

    async with async_session_factory() as db:
        try:
            await trigger_event(db, game_id, uuid.uuid4(), EventType.STORM)
            raise AssertionError("expected NotAGameMemberError")
        except NotAGameMemberError:
            pass


async def test_trigger_event_requires_running_game(db_session: AsyncSession) -> None:
    async with async_session_factory() as db:
        db.add(
            StationTemplate(
                name="EvtNotRunning Station",
                latitude=56.0,
                longitude=47.0,
                base_price="2000000.00",
                metadata_json={},
            )
        )
        await db.commit()

    creator_id = await _register("evtnotrunning@example.com")
    async with async_session_factory() as db:
        game = await create_game(db, creator_id, CreateGameRequest(name="EvtNotRunning"))
        game_id = game.id

    async with async_session_factory() as db:
        try:
            await trigger_event(db, game_id, creator_id, EventType.STORM)
            raise AssertionError("expected GameNotRunningError")
        except GameNotRunningError:
            pass


async def test_trigger_storm_creates_active_event_with_modifiers(db_session: AsyncSession) -> None:
    game_id, _station_id, owner_id = await _setup_owned_station("EvtStorm")

    async with async_session_factory() as db:
        event = await trigger_event(db, game_id, owner_id, EventType.STORM)

    assert event.status == EventStatus.ACTIVE
    assert event.ends_at > event.started_at
    assert event.modifiers_json["traffic_multiplier"] > 1.0

    async with async_session_factory() as db:
        history = await list_event_history(db, game_id)
    assert len(history) == 1
    assert history[0].id == event.id


async def test_trigger_road_works_closes_paired_edges(db_session: AsyncSession) -> None:
    game_id, _station_id, owner_id = await _setup_owned_station("EvtRoadWorks")

    async with async_session_factory() as db:
        node_a = RoadNode(latitude=56.0, longitude=47.0)
        node_b = RoadNode(latitude=56.01, longitude=47.01)
        db.add_all([node_a, node_b])
        await db.flush()
        edge_ab = RoadEdge(
            from_node_id=node_a.id,
            to_node_id=node_b.id,
            distance_km=5.0,
            max_speed_kmh=60.0,
            road_type="local",
        )
        edge_ba = RoadEdge(
            from_node_id=node_b.id,
            to_node_id=node_a.id,
            distance_km=5.0,
            max_speed_kmh=60.0,
            road_type="local",
        )
        db.add_all([edge_ab, edge_ba])
        await db.commit()

    async with async_session_factory() as db:
        event = await trigger_event(db, game_id, owner_id, EventType.ROAD_WORKS)

    assert "closed_edge_ids" in event.modifiers_json
    assert len(event.modifiers_json["closed_edge_ids"]) == 2

    async with async_session_factory() as db:
        edges = (await db.execute(select(RoadEdge))).scalars().all()
        assert all(edge.is_closed for edge in edges)


async def test_trigger_regulatory_inspection_fines_station_without_upgrades(
    db_session: AsyncSession,
) -> None:
    game_id, station_id, owner_id = await _setup_owned_station("EvtInspectFine")

    async with async_session_factory() as db:
        player_before = (
            await db.execute(select(GamePlayer).where(GamePlayer.game_id == game_id))
        ).scalar_one()
        balance_before = player_before.balance

    async with async_session_factory() as db:
        await trigger_event(db, game_id, owner_id, EventType.REGULATORY_INSPECTION)

    async with async_session_factory() as db:
        station = await db.get(GameStation, station_id)
        assert station is not None
        assert station.status == STATION_STATUS_INACTIVE

        player_after = (
            await db.execute(select(GamePlayer).where(GamePlayer.game_id == game_id))
        ).scalar_one()
        assert player_after.balance < balance_before

        fines = (
            (
                await db.execute(
                    select(FinancialTransaction).where(
                        FinancialTransaction.transaction_type == TRANSACTION_TYPE_EVENT_FINE
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(fines) == 1
        assert fines[0].amount < Decimal("0")


async def test_trigger_regulatory_inspection_spares_station_with_active_upgrade(
    db_session: AsyncSession,
) -> None:
    game_id, station_id, owner_id = await _setup_owned_station("EvtInspectSpare")

    async with async_session_factory() as db:
        upgrade = await purchase_upgrade(db, game_id, owner_id, station_id, UpgradeType.PARKING)
        upgrade_id = upgrade.id
    async with async_session_factory() as db:
        upgrade = await db.get(StationUpgrade, upgrade_id)
        assert upgrade is not None
        upgrade.status = UpgradeStatus.ACTIVE
        await db.commit()

    async with async_session_factory() as db:
        await trigger_event(db, game_id, owner_id, EventType.REGULATORY_INSPECTION)

    async with async_session_factory() as db:
        station = await db.get(GameStation, station_id)
        assert station is not None
        assert station.status == STATION_STATUS_ACTIVE

        fines = (
            (
                await db.execute(
                    select(FinancialTransaction).where(
                        FinancialTransaction.transaction_type == TRANSACTION_TYPE_EVENT_FINE
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(fines) == 0


async def test_trigger_refinery_breakdown_reduces_stock(db_session: AsyncSession) -> None:
    game_id, _station_id, owner_id = await _setup_owned_station("EvtRefineryBreak")

    async with async_session_factory() as db:
        refinery = Refinery(name="EvtRefineryBreak Refinery", latitude=56.05, longitude=47.05)
        db.add(refinery)
        await db.flush()
        fuel = RefineryFuel(
            refinery_id=refinery.id,
            game_id=game_id,
            fuel_type=FuelType.AI92,
            current_liters=Decimal("100000.00"),
            purchase_price=Decimal("42.00"),
            loading_speed=2000.0,
        )
        db.add(fuel)
        await db.commit()
        fuel_id = fuel.id

    async with async_session_factory() as db:
        await trigger_event(db, game_id, owner_id, EventType.REFINERY_BREAKDOWN)

    async with async_session_factory() as db:
        fuel = await db.get(RefineryFuel, fuel_id)
        assert fuel is not None
        assert fuel.current_liters < Decimal("100000.00")


async def test_trigger_city_festival_picks_a_region(db_session: AsyncSession) -> None:
    game_id, _station_id, owner_id = await _setup_owned_station("EvtFestival")

    async with async_session_factory() as db:
        event = await trigger_event(db, game_id, owner_id, EventType.CITY_FESTIVAL)

    assert event.region_json is not None
    assert "latitude" in event.region_json
    assert "radius_km" in event.region_json


async def test_get_active_event_effects_merges_multipliers_multiplicatively(
    db_session: AsyncSession,
) -> None:
    game_id, _station_id, owner_id = await _setup_owned_station("EvtMerge")

    async with async_session_factory() as db:
        await trigger_event(db, game_id, owner_id, EventType.STORM)
    async with async_session_factory() as db:
        await trigger_event(db, game_id, owner_id, EventType.SEVERE_STORM)

    async with async_session_factory() as db:
        modifiers, bonuses = await get_active_event_effects(db, game_id)

    assert modifiers.traffic_multiplier > 1.3 * 1.5
    assert bonuses == []


def test_list_attractiveness_bonuses_extracts_region_and_gate() -> None:
    event = GameEvent(
        game_id=uuid.uuid4(),
        event_type=EventType.TOURIST_SEASON,
        status=EventStatus.ACTIVE,
        region_json=None,
        modifiers_json={
            "attractiveness_bonus": 0.5,
            "attractiveness_upgrade_types": ["parking", "food_court"],
        },
        started_at=None,  # type: ignore[arg-type]
        ends_at=None,  # type: ignore[arg-type]
    )
    bonuses = list_attractiveness_bonuses([event])
    assert len(bonuses) == 1
    assert bonuses[0].bonus == 0.5
    assert bonuses[0].region is None
    assert bonuses[0].required_upgrade_types == ["parking", "food_court"]


def test_region_dataclass_round_trip() -> None:
    region = Region(latitude=56.0, longitude=47.0, radius_km=10.0)
    assert region.radius_km == 10.0
