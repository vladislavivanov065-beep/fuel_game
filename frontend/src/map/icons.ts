import L from 'leaflet'
import ambulanceImg from './ambulance.png'
import cargoTruckImg from './cargo_truck.png'
import fireTruckImg from './fire_truck.png'
import hatchbackImg from './hatchback.png'
import jeepImg from './jeep.png'
import marshrutkaImg from './marshrutka.png'
import motorcycleImg from './motorcycle.png'
import pickupImg from './pickup.png'
import policeImg from './police.png'
import trolleybusImg from './trolleybus.png'

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

// Все картинки нарисованы на одном холсте 1024x1536 (вид сверху, нос вверх),
// так что у всех одинаковое соотношение сторон — только высота ("длина
// машины" в пикселях на карте) отличается по типу.
const IMAGE_ASPECT_RATIO = 1024 / 1536

interface VehicleTypeShape {
  src: string
  lengthPx: number
  isEmergency: boolean
}

const VEHICLE_TYPE_SHAPES: Record<string, VehicleTypeShape> = {
  hatchback: { src: hatchbackImg, lengthPx: 20, isEmergency: false },
  jeep: { src: jeepImg, lengthPx: 22, isEmergency: false },
  pickup: { src: pickupImg, lengthPx: 24, isEmergency: false },
  motorcycle: { src: motorcycleImg, lengthPx: 14, isEmergency: false },
  marshrutka: { src: marshrutkaImg, lengthPx: 26, isEmergency: false },
  cargo_truck: { src: cargoTruckImg, lengthPx: 30, isEmergency: false },
  trolleybus: { src: trolleybusImg, lengthPx: 32, isEmergency: false },
  ambulance: { src: ambulanceImg, lengthPx: 24, isEmergency: true },
  police: { src: policeImg, lengthPx: 22, isEmergency: true },
  fire_truck: { src: fireTruckImg, lengthPx: 30, isEmergency: true },
}

export function vehicleIconForType(vehicleType: string, heading: number): L.DivIcon {
  const shape = VEHICLE_TYPE_SHAPES[vehicleType] ?? VEHICLE_TYPE_SHAPES.hatchback
  const height = shape.lengthPx
  const width = Math.round(height * IMAGE_ASPECT_RATIO)
  // Контейнер — квадрат по диагонали картинки, чтобы она не обрезалась при повороте.
  const size = Math.ceil(Math.hypot(width, height))
  const className = shape.isEmergency ? 'vehicle-marker-typed vehicle-marker-emergency' : 'vehicle-marker-typed'
  return L.divIcon({
    className,
    html: `<img src="${shape.src}" alt="" style="width:${width}px;height:${height}px;transform:rotate(${heading}deg);display:block;" />`,
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
