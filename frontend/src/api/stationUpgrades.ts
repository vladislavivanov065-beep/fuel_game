import { apiRequest } from './client'

export type UpgradeType =
  | 'pumps'
  | 'tanks'
  | 'shop'
  | 'food_court'
  | 'car_wash'
  | 'rating'
  | 'advertising'
  | 'parking'
  | 'loyalty_program'

export type UpgradeStatus = 'under_construction' | 'active' | 'expired'

export interface StationUpgradeInfo {
  upgrade_type: UpgradeType
  level: number
  status: UpgradeStatus | null
  next_level_cost: string
  build_minutes: number
  min_station_level: number
  completed_at: string | null
}

export interface StationUpgrade {
  id: string
  station_id: string
  upgrade_type: UpgradeType
  level: number
  status: UpgradeStatus
  started_at: string
  completed_at: string
}

export function listStationUpgrades(
  gameId: string,
  stationId: string,
): Promise<StationUpgradeInfo[]> {
  return apiRequest<StationUpgradeInfo[]>(`/api/games/${gameId}/stations/${stationId}/upgrades`)
}

export function purchaseStationUpgrade(
  gameId: string,
  stationId: string,
  upgradeType: UpgradeType,
): Promise<StationUpgrade> {
  return apiRequest<StationUpgrade>(`/api/games/${gameId}/stations/${stationId}/upgrades`, {
    method: 'POST',
    body: JSON.stringify({ upgrade_type: upgradeType }),
  })
}
