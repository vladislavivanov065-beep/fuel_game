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
