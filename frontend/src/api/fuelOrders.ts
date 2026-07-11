import { apiRequest } from './client'
import type { FuelType } from './gameStations'

export interface FuelOrderStop {
  station_id: string
  position: number
  fuel_type: FuelType
  liters: string
  delivered_liters: string
  status: string
}

export interface FuelOrder {
  id: string
  game_id: string
  player_id: string
  refinery_id: string
  status: string
  total_cost: string
  delivery_cost: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  stops: FuelOrderStop[]
}

export interface CreateFuelOrderPayload {
  refinery_id: string
  station_id: string
  fuel_type: FuelType
  liters: string
}

export function createFuelOrder(
  gameId: string,
  data: CreateFuelOrderPayload,
): Promise<FuelOrder> {
  return apiRequest<FuelOrder>(`/api/games/${gameId}/fuel-orders`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function listFuelOrders(gameId: string): Promise<FuelOrder[]> {
  return apiRequest<FuelOrder[]>(`/api/games/${gameId}/fuel-orders`)
}
