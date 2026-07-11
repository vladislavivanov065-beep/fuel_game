import { apiRequest } from './client'

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
}

export function listGameStations(gameId: string): Promise<GameStation[]> {
  return apiRequest<GameStation[]>(`/api/games/${gameId}/stations`)
}

export function purchaseStation(gameId: string, stationId: string): Promise<GameStation> {
  return apiRequest<GameStation>(`/api/games/${gameId}/stations/${stationId}/purchase`, {
    method: 'POST',
  })
}
