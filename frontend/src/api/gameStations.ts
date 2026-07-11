import { apiRequest } from './client'

export type FuelType = 'ai92' | 'ai95' | 'diesel'

export interface StationFuel {
  id: string
  fuel_type: FuelType
  current_liters: string
  reserved_liters: string
  capacity_liters: string
  retail_price: string
  average_purchase_price: string
  price_updated_at: string | null
}

export interface GameStation {
  id: string
  game_id: string
  station_template_id: string
  name: string
  latitude: number
  longitude: number
  owner_player_id: string | null
  owner_display_name: string | null
  owner_network_name: string | null
  owner_network_color: string | null
  purchase_price: string
  status: string
  level: number
  rating: number
  queue_length: number
  created_at: string
  fuels: StationFuel[]
}

export function listGameStations(gameId: string): Promise<GameStation[]> {
  return apiRequest<GameStation[]>(`/api/games/${gameId}/stations`)
}

export function purchaseStation(gameId: string, stationId: string): Promise<GameStation> {
  return apiRequest<GameStation>(`/api/games/${gameId}/stations/${stationId}/purchase`, {
    method: 'POST',
  })
}

export function setStationPrice(
  gameId: string,
  stationId: string,
  fuelType: FuelType,
  retailPrice: string,
): Promise<StationFuel> {
  return apiRequest<StationFuel>(`/api/games/${gameId}/stations/${stationId}/prices`, {
    method: 'PATCH',
    body: JSON.stringify({ fuel_type: fuelType, retail_price: retailPrice }),
  })
}

export function setNetworkPrice(
  gameId: string,
  fuelType: FuelType,
  retailPrice: string,
): Promise<{ updated_stations: number }> {
  return apiRequest<{ updated_stations: number }>(`/api/games/${gameId}/network/prices`, {
    method: 'PATCH',
    body: JSON.stringify({ fuel_type: fuelType, retail_price: retailPrice }),
  })
}
