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

export function interpolateVehiclePosition(
  vehicle: Vehicle,
  nowMs: number,
): { latitude: number; longitude: number } {
  // While queued/refueling the vehicle is stationary at the station — only
  // "driving" positions are derived from elapsed time against the route.
  if (vehicle.status !== 'driving') {
    return { latitude: vehicle.current_latitude, longitude: vehicle.current_longitude }
  }

  const elapsedMinutes = (nowMs - new Date(vehicle.started_at).getTime()) / 60000
  const points = vehicle.route_points

  if (points.length === 0) {
    return { latitude: vehicle.current_latitude, longitude: vehicle.current_longitude }
  }
  if (elapsedMinutes <= points[0].cumulative_minutes) {
    return { latitude: points[0].latitude, longitude: points[0].longitude }
  }

  for (let i = 0; i < points.length - 1; i++) {
    const previous = points[i]
    const current = points[i + 1]
    if (elapsedMinutes <= current.cumulative_minutes) {
      const span = current.cumulative_minutes - previous.cumulative_minutes
      const fraction = span === 0 ? 0 : (elapsedMinutes - previous.cumulative_minutes) / span
      return {
        latitude: previous.latitude + (current.latitude - previous.latitude) * fraction,
        longitude: previous.longitude + (current.longitude - previous.longitude) * fraction,
      }
    }
  }

  const last = points[points.length - 1]
  return { latitude: last.latitude, longitude: last.longitude }
}
