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

export interface RoadNode {
  id: string
  latitude: number
  longitude: number
}

export interface RoadEdge {
  id: string
  from_node_id: string
  to_node_id: string
  road_type: string
  is_closed: boolean
}

export interface TrafficLight {
  id: string
  road_node_id: string
  red_seconds: number
  yellow_seconds: number
  green_seconds: number
  offset_seconds: number
}

export interface MapData {
  stations: StationTemplate[]
  refineries: Refinery[]
  road_nodes: RoadNode[]
  road_edges: RoadEdge[]
  traffic_lights: TrafficLight[]
}

export function fetchMapData(): Promise<MapData> {
  return apiRequest<MapData>('/api/map')
}
