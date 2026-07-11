import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.db.models.game_room import GameStatus
from app.schemas.game_settings import GameSettings

if TYPE_CHECKING:
    from app.db.models.game_player import GamePlayer
    from app.db.models.game_room import GameRoom


class CreateGameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    settings: GameSettings = Field(default_factory=GameSettings)


class JoinGameRequest(BaseModel):
    invite_code: str = Field(min_length=1, max_length=16)


class SetReadyRequest(BaseModel):
    is_ready: bool


class GamePlayerResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    network_name: str | None
    network_color: str | None
    balance: Decimal
    net_worth: Decimal
    is_ready: bool
    is_admin: bool
    joined_at: datetime

    @classmethod
    def from_model(cls, player: "GamePlayer") -> "GamePlayerResponse":
        return cls(
            id=player.id,
            user_id=player.user_id,
            display_name=player.user.display_name,
            network_name=player.network_name,
            network_color=player.network_color,
            balance=player.balance,
            net_worth=player.net_worth,
            is_ready=player.is_ready,
            is_admin=player.is_admin,
            joined_at=player.joined_at,
        )


class GameSummaryResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: GameStatus
    creator_id: uuid.UUID
    invite_code: str
    player_count: int
    created_at: datetime

    @classmethod
    def from_model(cls, game: "GameRoom") -> "GameSummaryResponse":
        return cls(
            id=game.id,
            name=game.name,
            status=game.status,
            creator_id=game.creator_id,
            invite_code=game.invite_code,
            player_count=len(game.players),
            created_at=game.created_at,
        )


class GameDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: GameStatus
    invite_code: str
    creator_id: uuid.UUID
    settings: GameSettings
    players: list[GamePlayerResponse]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_model(cls, game: "GameRoom") -> "GameDetailResponse":
        return cls(
            id=game.id,
            name=game.name,
            status=game.status,
            invite_code=game.invite_code,
            creator_id=game.creator_id,
            settings=GameSettings.model_validate(game.settings_json),
            players=[GamePlayerResponse.from_model(p) for p in game.players],
            created_at=game.created_at,
            started_at=game.started_at,
            finished_at=game.finished_at,
        )


class InvitePreviewResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: GameStatus
    player_count: int

    @classmethod
    def from_model(cls, game: "GameRoom") -> "InvitePreviewResponse":
        return cls(
            id=game.id,
            name=game.name,
            status=game.status,
            player_count=len(game.players),
        )
