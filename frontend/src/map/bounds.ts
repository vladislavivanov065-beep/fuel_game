import L from 'leaflet'

// Approximate bounding box of the Mari El Republic.
export const MARI_EL_BOUNDS = L.latLngBounds(
  L.latLng(55.7, 45.5),
  L.latLng(57.4, 50.3),
)

export const MARI_EL_CENTER: L.LatLngTuple = [56.6389, 47.8845]
export const MARI_EL_DEFAULT_ZOOM = 8
export const MARI_EL_MIN_ZOOM = 7
