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
  route_points: TruckRoutePoint[]
  total_distance_km: number
  total_travel_time_minutes: number
  started_at: string
  updated_at: string
}

export function listTrucks(gameId: string): Promise<Truck[]> {
  return apiRequest<Truck[]>(`/api/games/${gameId}/trucks`)
}

export function interpolateTruckPosition(
  truck: Truck,
  nowMs: number,
): { latitude: number; longitude: number } {
  const elapsedMinutes = (nowMs - new Date(truck.started_at).getTime()) / 60000
  const points = truck.route_points

  if (points.length === 0) {
    return { latitude: truck.current_latitude, longitude: truck.current_longitude }
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
