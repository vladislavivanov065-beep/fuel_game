from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.station_template import StationTemplate
from app.main import app


@asynccontextmanager
async def _registered_client(email: str, display_name: str) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/register",
            json={"email": email, "password": "correcthorsebattery", "display_name": display_name},
        )
        assert response.status_code == 201
        yield client


async def _seed_two_stations(db_session: AsyncSession, prefix: str) -> None:
    db_session.add_all(
        [
            StationTemplate(
                name=f"{prefix} Station A",
                latitude=56.0,
                longitude=47.0,
                base_price="2000000.00",
                metadata_json={},
            ),
            StationTemplate(
                name=f"{prefix} Station B",
                latitude=56.1,
                longitude=47.1,
                base_price="2000000.00",
                metadata_json={},
            ),
        ]
    )
    await db_session.commit()


async def _setup_two_player_game(
    creator: AsyncClient, other: AsyncClient, name: str
) -> tuple[dict, str, str]:
    """Returns (game, seller_station_id, buyer_station_id) with creator owning A, other owning B."""
    game = (await creator.post("/api/games", json={"name": name})).json()
    await other.post(f"/api/games/{game['id']}/join", json={"invite_code": game["invite_code"]})
    await creator.post(f"/api/games/{game['id']}/start")

    stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
    station_a_id, station_b_id = stations[0]["id"], stations[1]["id"]

    await creator.post(f"/api/games/{game['id']}/stations/{station_a_id}/purchase")
    await other.post(f"/api/games/{game['id']}/stations/{station_b_id}/purchase")

    return game, station_a_id, station_b_id


async def test_create_list_and_accept_station_sale_via_api(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_two_stations(db_session, "TradeApi1")

    async with (
        _registered_client("tradeapi1creator@example.com", "Creator") as creator,
        _registered_client("tradeapi1other@example.com", "Other") as other,
    ):
        game, seller_station_id, _buyer_station_id = await _setup_two_player_game(
            creator, other, "TradeApi Game 1"
        )

        create_response = await creator.post(
            f"/api/games/{game['id']}/trades",
            json={
                "offer_type": "station_sale",
                "terms": {"station_id": seller_station_id, "price": "1000000.00"},
            },
        )
        assert create_response.status_code == 201
        trade = create_response.json()
        assert trade["status"] == "pending"

        list_response = await other.get(f"/api/games/{game['id']}/trades")
        assert list_response.status_code == 200
        assert any(t["id"] == trade["id"] for t in list_response.json())

        accept_response = await other.post(
            f"/api/games/{game['id']}/trades/{trade['id']}/accept", json={}
        )
        assert accept_response.status_code == 200
        assert accept_response.json()["status"] == "accepted"

        stations = (await creator.get(f"/api/games/{game['id']}/stations")).json()
        sold_station = next(s for s in stations if s["id"] == seller_station_id)
        assert sold_station["owner_display_name"] == "Other"


async def test_reject_trade_via_api(client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed_two_stations(db_session, "TradeApi2")

    async with (
        _registered_client("tradeapi2creator@example.com", "Creator") as creator,
        _registered_client("tradeapi2other@example.com", "Other") as other,
    ):
        game, seller_station_id, _buyer_station_id = await _setup_two_player_game(
            creator, other, "TradeApi Game 2"
        )
        players = (await creator.get(f"/api/games/{game['id']}")).json()["players"]
        other_player_id = next(p["user_id"] for p in players if p["display_name"] == "Other")

        trade = (
            await creator.post(
                f"/api/games/{game['id']}/trades",
                json={
                    "offer_type": "station_sale",
                    "terms": {"station_id": seller_station_id, "price": "1000000.00"},
                    "buyer_user_id": other_player_id,
                },
            )
        ).json()
        assert trade["buyer_id"] is not None

        reject_response = await other.post(f"/api/games/{game['id']}/trades/{trade['id']}/reject")
        assert reject_response.status_code == 200
        assert reject_response.json()["status"] == "rejected"


async def test_cancel_trade_via_api(client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed_two_stations(db_session, "TradeApi3")

    async with (
        _registered_client("tradeapi3creator@example.com", "Creator") as creator,
        _registered_client("tradeapi3other@example.com", "Other") as other,
    ):
        game, seller_station_id, _buyer_station_id = await _setup_two_player_game(
            creator, other, "TradeApi Game 3"
        )

        trade = (
            await creator.post(
                f"/api/games/{game['id']}/trades",
                json={
                    "offer_type": "station_sale",
                    "terms": {"station_id": seller_station_id, "price": "1000000.00"},
                },
            )
        ).json()

        cancel_response = await creator.post(f"/api/games/{game['id']}/trades/{trade['id']}/cancel")
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "cancelled"

        forbidden_cancel = await other.post(f"/api/games/{game['id']}/trades/{trade['id']}/cancel")
        assert forbidden_cancel.status_code in (403, 409)


async def test_counter_trade_via_api(client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed_two_stations(db_session, "TradeApi4")

    async with (
        _registered_client("tradeapi4creator@example.com", "Creator") as creator,
        _registered_client("tradeapi4other@example.com", "Other") as other,
    ):
        game, seller_station_id, _buyer_station_id = await _setup_two_player_game(
            creator, other, "TradeApi Game 4"
        )
        players = (await creator.get(f"/api/games/{game['id']}")).json()["players"]
        other_player_id = next(p["user_id"] for p in players if p["display_name"] == "Other")

        trade = (
            await creator.post(
                f"/api/games/{game['id']}/trades",
                json={
                    "offer_type": "station_sale",
                    "terms": {"station_id": seller_station_id, "price": "1500000.00"},
                    "buyer_user_id": other_player_id,
                },
            )
        ).json()

        counter_response = await other.post(
            f"/api/games/{game['id']}/trades/{trade['id']}/counter",
            json={"terms": {"station_id": seller_station_id, "price": "1000000.00"}},
        )
        assert counter_response.status_code == 200
        countered = counter_response.json()
        assert countered["id"] != trade["id"]
        assert countered["terms"]["price"] == "1000000.00"

        offers = (await creator.get(f"/api/games/{game['id']}/trades")).json()
        by_id = {o["id"]: o for o in offers}
        assert by_id[trade["id"]]["status"] == "rejected"
        assert by_id[countered["id"]]["status"] == "pending"


async def test_create_trade_for_station_not_owned_returns_409(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_two_stations(db_session, "TradeApi5")

    async with (
        _registered_client("tradeapi5creator@example.com", "Creator") as creator,
        _registered_client("tradeapi5other@example.com", "Other") as other,
    ):
        game, seller_station_id, _buyer_station_id = await _setup_two_player_game(
            creator, other, "TradeApi Game 5"
        )

        response = await other.post(
            f"/api/games/{game['id']}/trades",
            json={
                "offer_type": "station_sale",
                "terms": {"station_id": seller_station_id, "price": "1000000.00"},
            },
        )
        assert response.status_code == 409
