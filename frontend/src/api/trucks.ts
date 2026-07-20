import { apiRequest } from './client'

export interface TruckRoutePoint {
  latitude: number
  longitude: number
  cumulative_minutes: number
}

export interface Truck {
  id: string
  game_id: string
  fuel_order_id: string
  status: string
  route_progress: number
  current_latitude: number
  current_longitude: number
  heading: number
  route_points: TruckRoutePoint[]
  total_distance_km: number
  total_travel_time_minutes: number
  started_at: string
  updated_at: string
}

export function listTrucks(gameId: string): Promise<Truck[]> {
  return apiRequest<Truck[]>(`/api/games/${gameId}/trucks`)
}

export function interpolateTruckPosition(truck: Truck): { latitude: number; longitude: number } {
  // Этап 14.3: see interpolateVehiclePosition in api/vehicles.ts — trucks are
  // now physics-simulated (car-following + traffic lights + closures) too,
  // so the client shows the server's last position instead of extrapolating.
  return { latitude: truck.current_latitude, longitude: truck.current_longitude }
}
