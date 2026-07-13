import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.db.models.station_upgrade import UpgradeStatus, UpgradeType

if TYPE_CHECKING:
    from app.db.models.station_upgrade import StationUpgrade
    from app.services.station_upgrade_service import UpgradeInfo


class PurchaseStationUpgradeRequest(BaseModel):
    upgrade_type: UpgradeType


class StationUpgradeResponse(BaseModel):
    id: uuid.UUID
    station_id: uuid.UUID
    upgrade_type: UpgradeType
    level: int
    status: UpgradeStatus
    started_at: datetime
    completed_at: datetime

    @classmethod
    def from_model(cls, upgrade: "StationUpgrade") -> "StationUpgradeResponse":
        return cls(
            id=upgrade.id,
            station_id=upgrade.station_id,
            upgrade_type=upgrade.upgrade_type,
            level=upgrade.level,
            status=upgrade.status,
            started_at=upgrade.started_at,
            completed_at=upgrade.completed_at,
        )


class StationUpgradeInfoResponse(BaseModel):
    upgrade_type: UpgradeType
    level: int
    status: UpgradeStatus | None
    next_level_cost: Decimal
    build_minutes: float
    min_station_level: int
    completed_at: datetime | None

    @classmethod
    def from_info(cls, info: "UpgradeInfo") -> "StationUpgradeInfoResponse":
        return cls(
            upgrade_type=info.upgrade_type,
            level=info.level,
            status=info.status,
            next_level_cost=info.next_level_cost,
            build_minutes=info.build_minutes,
            min_station_level=info.min_station_level,
            completed_at=info.completed_at,
        )
