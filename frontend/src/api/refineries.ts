import { apiRequest } from './client'
import type { FuelType } from './gameStations'

export interface RefineryFuelStock {
  fuel_type: FuelType
  current_liters: string
  purchase_price: string
  loading_speed: number
}

export interface RefineryWithFuels {
  id: string
  name: string
  latitude: number
  longitude: number
  fuels: RefineryFuelStock[]
}

export function listGameRefineries(gameId: string): Promise<RefineryWithFuels[]> {
  return apiRequest<RefineryWithFuels[]>(`/api/games/${gameId}/refineries`)
}
