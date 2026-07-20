import L from 'leaflet'

export const stationIcon = L.divIcon({
  className: 'station-marker',
  html: '<div style="width:14px;height:14px;border-radius:50%;background:#9e9e9e;border:2px solid #444;"></div>',
  iconSize: [14, 14],
  iconAnchor: [7, 7],
})

export const refineryIcon = L.divIcon({
  className: 'refinery-marker',
  html: '<div style="width:26px;height:26px;background:#b35900;border:3px solid #663300;border-radius:4px;"></div>',
  iconSize: [26, 26],
  iconAnchor: [13, 13],
})

export const truckIcon = L.divIcon({
  className: 'truck-marker',
  html: '<div style="width:12px;height:12px;border-radius:50%;background:#ff8c00;border:2px solid #8a4b00;"></div>',
  iconSize: [12, 12],
  iconAnchor: [6, 6],
})

interface VehicleTypeShape {
  width: number
  height: number
  color: string
  borderColor: string
  borderRadius: string
  isEmergency: boolean
}

const VEHICLE_TYPE_SHAPES: Record<string, VehicleTypeShape> = {
  hatchback: {
    width: 8,
    height: 5,
    color: '#1976d2',
    borderColor: '#0d3c73',
    borderRadius: '2px',
    isEmergency: false,
  },
  jeep: {
    width: 9,
    height: 6,
    color: '#4a5f3a',
    borderColor: '#28351f',
    borderRadius: '2px',
    isEmergency: false,
  },
  pickup: {
    width: 10,
    height: 5,
    color: '#8d6e63',
    borderColor: '#4e342e',
    borderRadius: '1px',
    isEmergency: false,
  },
  motorcycle: {
    width: 5,
    height: 3,
    color: '#212121',
    borderColor: '#000000',
    borderRadius: '2px',
    isEmergency: false,
  },
  marshrutka: {
    width: 12,
    height: 6,
    color: '#fdd835',
    borderColor: '#8a7000',
    borderRadius: '1px',
    isEmergency: false,
  },
  cargo_truck: {
    width: 14,
    height: 6,
    color: '#6d4c41',
    borderColor: '#3e2723',
    borderRadius: '1px',
    isEmergency: false,
  },
  trolleybus: {
    width: 15,
    height: 6,
    color: '#00897b',
    borderColor: '#004d40',
    borderRadius: '1px',
    isEmergency: false,
  },
  ambulance: {
    width: 10,
    height: 6,
    color: '#f5f5f5',
    borderColor: '#c62828',
    borderRadius: '1px',
    isEmergency: true,
  },
  police: {
    width: 9,
    height: 6,
    color: '#1a237e',
    borderColor: '#0d1450',
    borderRadius: '2px',
    isEmergency: true,
  },
  fire_truck: {
    width: 13,
    height: 6,
    color: '#e53935',
    borderColor: '#8e0000',
    borderRadius: '1px',
    isEmergency: true,
  },
}

export function vehicleIconForType(vehicleType: string, heading: number): L.DivIcon {
  const shape = VEHICLE_TYPE_SHAPES[vehicleType] ?? VEHICLE_TYPE_SHAPES.hatchback
  const size = Math.max(shape.width, shape.height) + 4
  const className = shape.isEmergency ? 'vehicle-marker-typed vehicle-marker-emergency' : 'vehicle-marker-typed'
  return L.divIcon({
    className,
    html: `<div style="width:${shape.width}px;height:${shape.height}px;background:${shape.color};border:1px solid ${shape.borderColor};border-radius:${shape.borderRadius};transform:rotate(${heading}deg);"></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

const HEX_COLOR_PATTERN = /^#[0-9A-Fa-f]{6}$/

export function ownedStationIcon(color: string): L.DivIcon {
  const safeColor = HEX_COLOR_PATTERN.test(color) ? color : '#9e9e9e'
  return L.divIcon({
    className: 'station-marker-owned',
    html: `<div style="width:16px;height:16px;border-radius:50%;background:${safeColor};border:2px solid #222;"></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  })
}
