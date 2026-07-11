import { useQuery } from '@tanstack/react-query'
import 'leaflet/dist/leaflet.css'
import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet'
import { fetchMapData } from '../api/map'
import {
  MARI_EL_BOUNDS,
  MARI_EL_CENTER,
  MARI_EL_DEFAULT_ZOOM,
  MARI_EL_MIN_ZOOM,
} from '../map/bounds'
import { refineryIcon, stationIcon } from '../map/icons'

export function MapPage() {
  const { data, isLoading, isError } = useQuery({ queryKey: ['map'], queryFn: fetchMapData })

  return (
    <main>
      <h1>Карта Республики Марий Эл</h1>
      {isLoading && <p>Loading map...</p>}
      {isError && <p role="alert">Failed to load map data.</p>}
      <div style={{ height: '70vh', width: '100%' }}>
        <MapContainer
          center={MARI_EL_CENTER}
          zoom={MARI_EL_DEFAULT_ZOOM}
          minZoom={MARI_EL_MIN_ZOOM}
          maxBounds={MARI_EL_BOUNDS}
          maxBoundsViscosity={1.0}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {data?.stations.map((station) => (
            <Marker
              key={station.id}
              position={[station.latitude, station.longitude]}
              icon={stationIcon}
            >
              <Popup>
                <strong>{station.name}</strong>
                <br />
                Свободна
                <br />
                Стоимость: {station.base_price}
                <br />
                {String(station.metadata_json.settlement ?? '')}
              </Popup>
            </Marker>
          ))}
          {data?.refineries.map((refinery) => (
            <Marker
              key={refinery.id}
              position={[refinery.latitude, refinery.longitude]}
              icon={refineryIcon}
            >
              <Popup>
                <strong>{refinery.name}</strong>
                <br />
                НПЗ / Нефтебаза
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>
    </main>
  )
}
