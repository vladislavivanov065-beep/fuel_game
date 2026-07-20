import { apiRequest } from './client'

export interface VehicleRoutePoint {
  latitude: number
  longitude: number
  cumulative_minutes: number
}

export interface Vehicle {
  id: string
  game_id: string
  driver_type: string
  vehicle_type: string
  fuel_type: string
  status: string
  route_progress: number
  current_latitude: number
  current_longitude: number
  heading: number
  route_points: VehicleRoutePoint[]
  total_distance_km: number
  total_travel_time_minutes: number
  fuel_liters: string
  tank_capacity_liters: string
  chosen_station_id: string | null
  started_at: string
  updated_at: string
}

export function listVehicles(gameId: string): Promise<Vehicle[]> {
  return apiRequest<Vehicle[]>(`/api/games/${gameId}/vehicles`)
}

export function interpolateVehiclePosition(vehicle: Vehicle): {
  latitude: number
  longitude: number
} {
  // Этап 14.3: position is no longer a pure function of elapsed time (a
  // vehicle can be stopped at a red light or queued behind another car), so
  // the client just shows the server's last physics-simulated position
  // instead of extrapolating — the backend now broadcasts every tick (1s) to
  // keep this visually smooth.
  return { latitude: vehicle.current_latitude, longitude: vehicle.current_longitude }
}
