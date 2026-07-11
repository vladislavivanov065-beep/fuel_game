import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import 'leaflet/dist/leaflet.css'
import { Link, useParams } from 'react-router-dom'
import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet'
import { ApiError } from '../api/client'
import { getGame } from '../api/games'
import { listGameStations, purchaseStation } from '../api/gameStations'
import {
  MARI_EL_BOUNDS,
  MARI_EL_CENTER,
  MARI_EL_DEFAULT_ZOOM,
  MARI_EL_MIN_ZOOM,
} from '../map/bounds'
import { ownedStationIcon, stationIcon } from '../map/icons'
import { useAuthStore } from '../stores/authStore'
import { useGameSocket } from '../websocket/useGameSocket'

export function GameMapPage() {
  const { gameId } = useParams<{ gameId: string }>()
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [error, setError] = useState<string | null>(null)
  const [busyStationId, setBusyStationId] = useState<string | null>(null)

  const { data: stations, isLoading } = useQuery({
    queryKey: ['gameStations', gameId],
    queryFn: () => listGameStations(gameId ?? ''),
    enabled: Boolean(gameId),
  })

  const { data: game } = useQuery({
    queryKey: ['game', gameId],
    queryFn: () => getGame(gameId ?? ''),
    enabled: Boolean(gameId),
  })

  const myPlayerId = game?.players.find((p) => p.user_id === user?.id)?.id

  useGameSocket(gameId, (event) => {
    if (event.event === 'station.purchased' || event.event === 'player.updated') {
      void queryClient.invalidateQueries({ queryKey: ['gameStations', gameId] })
      void queryClient.invalidateQueries({ queryKey: ['game', gameId] })
    }
  })

  async function handlePurchase(stationId: string): Promise<void> {
    if (!gameId) return
    setBusyStationId(stationId)
    setError(null)
    try {
      await purchaseStation(gameId, stationId)
      await queryClient.invalidateQueries({ queryKey: ['gameStations', gameId] })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to purchase station')
    } finally {
      setBusyStationId(null)
    }
  }

  return (
    <main>
      <h1>Game map</h1>
      <p>
        <Link to={`/games/${gameId}`}>Back to lobby</Link>
      </p>
      {isLoading && <p>Loading stations...</p>}
      {error && <p role="alert">{error}</p>}
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
          {stations?.map((station) => {
            const isOwnedByMe =
              myPlayerId !== undefined && station.owner_player_id === myPlayerId
            const icon = station.owner_network_color
              ? ownedStationIcon(station.owner_network_color)
              : stationIcon
            return (
              <Marker key={station.id} position={[station.latitude, station.longitude]} icon={icon}>
                <Popup>
                  <strong>{station.name}</strong>
                  <br />
                  {station.owner_display_name
                    ? `Owned by ${station.owner_display_name}${
                        station.owner_network_name ? ` (${station.owner_network_name})` : ''
                      }`
                    : 'Free'}
                  <br />
                  Price: {station.purchase_price}
                  {!station.owner_player_id && (
                    <>
                      <br />
                      <button
                        type="button"
                        onClick={() => void handlePurchase(station.id)}
                        disabled={busyStationId === station.id}
                      >
                        {busyStationId === station.id ? 'Buying...' : 'Buy'}
                      </button>
                    </>
                  )}
                  {isOwnedByMe && (
                    <>
                      <br />
                      (You own this station)
                    </>
                  )}
                </Popup>
              </Marker>
            )
          })}
        </MapContainer>
      </div>
    </main>
  )
}
