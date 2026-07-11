import { apiRequest } from './client'

export type GameStatus = 'lobby' | 'running' | 'paused' | 'finished' | 'archived'

export interface GamePlayer {
  id: string
  user_id: string
  display_name: string
  network_name: string | null
  network_color: string | null
  balance: string
  net_worth: string
  is_ready: boolean
  is_admin: boolean
  joined_at: string
}

export interface GameSettings {
  is_private: boolean
  starting_balance: string
  free_station_price: string
  game_speed: number
  traffic_intensity: number
  event_frequency: number
  purchase_price_coefficient: number
  difficulty: string
  max_active_vehicles: number
  truck_speed_kmh: number
  starting_station_capacity_liters: string
  trading_enabled: boolean
  allow_join_after_start: boolean
  duration_minutes: number
  win_condition: string
}

export interface GameDetail {
  id: string
  name: string
  status: GameStatus
  invite_code: string
  creator_id: string
  settings: GameSettings
  players: GamePlayer[]
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface GameSummary {
  id: string
  name: string
  status: GameStatus
  creator_id: string
  invite_code: string
  player_count: number
  created_at: string
}

export interface InvitePreview {
  id: string
  name: string
  status: GameStatus
  player_count: number
}

export function createGame(name: string): Promise<GameDetail> {
  return apiRequest<GameDetail>('/api/games', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

export function listGames(): Promise<GameSummary[]> {
  return apiRequest<GameSummary[]>('/api/games')
}

export function getGame(gameId: string): Promise<GameDetail> {
  return apiRequest<GameDetail>(`/api/games/${gameId}`)
}

export function resolveInviteCode(inviteCode: string): Promise<InvitePreview> {
  return apiRequest<InvitePreview>(`/api/games/resolve/${inviteCode}`)
}

export function joinGame(gameId: string, inviteCode: string): Promise<GameDetail> {
  return apiRequest<GameDetail>(`/api/games/${gameId}/join`, {
    method: 'POST',
    body: JSON.stringify({ invite_code: inviteCode }),
  })
}

export function leaveGame(gameId: string): Promise<void> {
  return apiRequest<void>(`/api/games/${gameId}/leave`, { method: 'POST' })
}

export function setReady(gameId: string, isReady: boolean): Promise<GamePlayer> {
  return apiRequest<GamePlayer>(`/api/games/${gameId}/ready`, {
    method: 'POST',
    body: JSON.stringify({ is_ready: isReady }),
  })
}

export function startGame(gameId: string): Promise<GameDetail> {
  return apiRequest<GameDetail>(`/api/games/${gameId}/start`, { method: 'POST' })
}
