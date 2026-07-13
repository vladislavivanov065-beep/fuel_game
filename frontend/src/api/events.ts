import { apiRequest } from './client'

export type EventType =
  | 'storm'
  | 'severe_storm'
  | 'fuel_riot'
  | 'economic_crisis'
  | 'oil_price_drop'
  | 'road_works'
  | 'city_festival'
  | 'tourist_season'
  | 'regulatory_inspection'
  | 'refinery_breakdown'

export type EventStatusValue = 'active' | 'expired'

export interface EventRegion {
  latitude: number
  longitude: number
  radius_km: number
}

export interface GameEvent {
  id: string
  game_id: string
  event_type: EventType
  status: EventStatusValue
  region: EventRegion | null
  modifiers: Record<string, unknown>
  started_at: string
  ends_at: string
}

export function listActiveEvents(gameId: string): Promise<GameEvent[]> {
  return apiRequest<GameEvent[]>(`/api/games/${gameId}/events`)
}

export function listEventHistory(gameId: string): Promise<GameEvent[]> {
  return apiRequest<GameEvent[]>(`/api/games/${gameId}/events/history`)
}

export function triggerEvent(gameId: string, eventType: EventType): Promise<GameEvent> {
  return apiRequest<GameEvent>(`/api/games/${gameId}/events`, {
    method: 'POST',
    body: JSON.stringify({ event_type: eventType }),
  })
}
