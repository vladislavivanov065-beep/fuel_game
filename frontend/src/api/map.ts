import { apiRequest } from './client'

export interface StationTemplate {
  id: string
  osm_id: string | null
  name: string
  latitude: number
  longitude: number
  base_price: string
  metadata_json: Record<string, unknown>
}

export interface Refinery {
  id: string
  name: string
  latitude: number
  longitude: number
}

export interface MapData {
  stations: StationTemplate[]
  refineries: Refinery[]
}

export function fetchMapData(): Promise<MapData> {
  return apiRequest<MapData>('/api/map')
}
