import { apiRequest } from './client'

export interface RoadAccident {
  id: string
  game_id: string
  road_edge_id: string
  severity: 'minor' | 'major'
  started_at: string
  ends_at: string
}

export function listActiveAccidents(gameId: string): Promise<RoadAccident[]> {
  return apiRequest<RoadAccident[]>(`/api/games/${gameId}/accidents`)
}
