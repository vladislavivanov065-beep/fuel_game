import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_current_user
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.fuel_order import (
    CreateFuelOrderRequest,
    FuelOrderResponse,
    RefineryWithFuelsResponse,
)
from app.schemas.truck import TruckResponse
from app.services import fuel_order_service, game_service, refinery_service
from app.websocket.connection_manager import connection_manager

router = APIRouter(prefix="/api/games/{game_id}", tags=["fuel-orders"])


@router.get("/refineries", response_model=list[RefineryWithFuelsResponse])
async def list_refineries(
    game_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[RefineryWithFuelsResponse]:
    try:
        await game_service.get_game_for_member(db, game_id, user.id)
    except game_service.GameNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found") from exc
    except game_service.NotAGameMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        ) from exc

    items = await refinery_service.list_refineries_with_fuel_for_game(db, game_id)
    return [RefineryWithFuelsResponse.from_model(item) for item in items]


@router.post("/fuel-orders", response_model=FuelOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_fuel_order(
    game_id: uuid.UUID,
    data: CreateFuelOrderRequest,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> FuelOrderResponse:
    stops = [
        fuel_order_service.FuelOrderStopRequest(
            station_id=stop.station_id, fuel_type=stop.fuel_type, liters=stop.liters
        )
        for stop in data.stops
    ]
    try:
        order = await fuel_order_service.create_fuel_order(
            db, game_id, user.id, data.refinery_id, stops
        )
    except fuel_order_service.GameNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found") from exc
    except fuel_order_service.GameNotRunningError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Game is not running"
        ) from exc
    except fuel_order_service.NotAGameMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        ) from exc
    except fuel_order_service.RefineryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Refinery not found"
        ) from exc
    except fuel_order_service.StationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Station not found"
        ) from exc
    except fuel_order_service.StationNotOwnedByPlayerError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this station"
        ) from exc
    except fuel_order_service.FuelTypeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Fuel type not found"
        ) from exc
    except fuel_order_service.TruckCapacityExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Order exceeds truck capacity",
        ) from exc
    except fuel_order_service.StationCapacityExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Station tank capacity exceeded"
        ) from exc
    except fuel_order_service.InsufficientRefineryStockError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Refinery does not have enough fuel"
        ) from exc
    except fuel_order_service.InsufficientFundsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Insufficient funds"
        ) from exc
    except fuel_order_service.EmptyOrderError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Order has no stops"
        ) from exc
    except fuel_order_service.RouteNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="No route available to one or more stops"
        ) from exc

    await connection_manager.broadcast(
        game_id,
        "fuel_order.created",
        {
            "order_id": str(order.id),
            "player_id": str(order.player_id),
            "refinery_id": str(order.refinery_id),
            "total_cost": str(order.total_cost),
            "completed_at": order.completed_at.isoformat() if order.completed_at else None,
        },
    )

    return FuelOrderResponse.from_model(order)


@router.get("/fuel-orders", response_model=list[FuelOrderResponse])
async def list_my_fuel_orders(
    game_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[FuelOrderResponse]:
    try:
        orders = await fuel_order_service.list_my_fuel_orders(db, game_id, user.id)
    except fuel_order_service.NotAGameMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        ) from exc

    return [FuelOrderResponse.from_model(order) for order in orders]


@router.get("/trucks", response_model=list[TruckResponse])
async def list_my_trucks(
    game_id: uuid.UUID,
    user: Annotated[User, Depends(require_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[TruckResponse]:
    try:
        trucks = await fuel_order_service.list_my_trucks(db, game_id, user.id)
    except fuel_order_service.NotAGameMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this game"
        ) from exc

    return [TruckResponse.from_model(truck) for truck in trucks]
