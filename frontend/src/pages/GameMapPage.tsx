import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import 'leaflet/dist/leaflet.css'
import { Link, useParams } from 'react-router-dom'
import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet'
import { ApiError } from '../api/client'
import { listMyTransactions } from '../api/finance'
import { createFuelOrder, listFuelOrders } from '../api/fuelOrders'
import { getGame } from '../api/games'
import {
  type FuelType,
  type GameStation,
  listGameStations,
  purchaseStation,
  setNetworkPrice,
  setStationPrice,
} from '../api/gameStations'
import { listGameRefineries } from '../api/refineries'
import { FuelOrdersPanel } from '../components/FuelOrdersPanel'
import { IncomeChart } from '../components/IncomeChart'
import {
  MARI_EL_BOUNDS,
  MARI_EL_CENTER,
  MARI_EL_DEFAULT_ZOOM,
  MARI_EL_MIN_ZOOM,
} from '../map/bounds'
import { ownedStationIcon, refineryIcon, stationIcon } from '../map/icons'
import { useAuthStore } from '../stores/authStore'
import { useGameSocket } from '../websocket/useGameSocket'

const FUEL_LABELS: Record<FuelType, string> = {
  ai92: 'АИ-92',
  ai95: 'АИ-95',
  diesel: 'Дизель',
}

function StationPriceEditor({
  gameId,
  station,
  onSaved,
}: {
  gameId: string
  station: GameStation
  onSaved: () => void
}) {
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [busyFuel, setBusyFuel] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleSave(fuelType: FuelType): Promise<void> {
    const value = drafts[fuelType]
    if (!value) return
    setBusyFuel(fuelType)
    setError(null)
    try {
      await setStationPrice(gameId, station.id, fuelType, value)
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to update price')
    } finally {
      setBusyFuel(null)
    }
  }

  return (
    <div style={{ marginTop: 8 }}>
      {error && (
        <p role="alert" style={{ color: 'crimson', fontSize: 12 }}>
          {error}
        </p>
      )}
      {station.fuels.map((fuel) => (
        <div key={fuel.id} style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
          <span style={{ minWidth: 56 }}>{FUEL_LABELS[fuel.fuel_type]}</span>
          <span>{fuel.retail_price} ₽</span>
          <input
            type="number"
            step="0.01"
            placeholder="Новая цена"
            style={{ width: 80 }}
            value={drafts[fuel.fuel_type] ?? ''}
            onChange={(e) =>
              setDrafts((d) => ({ ...d, [fuel.fuel_type]: e.target.value }))
            }
          />
          <button
            type="button"
            onClick={() => void handleSave(fuel.fuel_type)}
            disabled={busyFuel === fuel.fuel_type || !drafts[fuel.fuel_type]}
          >
            {busyFuel === fuel.fuel_type ? '...' : 'OK'}
          </button>
        </div>
      ))}
    </div>
  )
}

function NetworkPriceEditor({ gameId, onSaved }: { gameId: string; onSaved: () => void }) {
  const [fuelType, setFuelType] = useState<FuelType>('ai92')
  const [price, setPrice] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleApply(): Promise<void> {
    if (!price) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = await setNetworkPrice(gameId, fuelType, price)
      setMessage(`Обновлено станций: ${result.updated_stations}`)
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to update network price')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 16, marginBottom: 16 }}>
      <h3 style={{ margin: '0 0 8px', fontSize: 16 }}>Цена по всей сети</h3>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <select value={fuelType} onChange={(e) => setFuelType(e.target.value as FuelType)}>
          {Object.entries(FUEL_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <input
          type="number"
          step="0.01"
          placeholder="Цена"
          style={{ width: 100 }}
          value={price}
          onChange={(e) => setPrice(e.target.value)}
        />
        <button type="button" onClick={() => void handleApply()} disabled={busy || !price}>
          {busy ? 'Применяю...' : 'Применить'}
        </button>
      </div>
      {message && <p style={{ fontSize: 12, color: 'var(--text)' }}>{message}</p>}
      {error && (
        <p role="alert" style={{ fontSize: 12, color: 'crimson' }}>
          {error}
        </p>
      )}
    </div>
  )
}

function RefineryOrderForm({
  gameId,
  refineryId,
  myStations,
  onOrdered,
}: {
  gameId: string
  refineryId: string
  myStations: GameStation[]
  onOrdered: () => void
}) {
  const [stationId, setStationId] = useState(myStations[0]?.id ?? '')
  const [fuelType, setFuelType] = useState<FuelType>('ai92')
  const [liters, setLiters] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  async function handleSubmit(): Promise<void> {
    if (!stationId || !liters) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await createFuelOrder(gameId, {
        refinery_id: refineryId,
        station_id: stationId,
        fuel_type: fuelType,
        liters,
      })
      setMessage('Заказ оформлен')
      setLiters('')
      onOrdered()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create fuel order')
    } finally {
      setBusy(false)
    }
  }

  if (myStations.length === 0) {
    return <p style={{ fontSize: 12 }}>У вас пока нет своих АЗС.</p>
  }

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <select value={stationId} onChange={(e) => setStationId(e.target.value)}>
          {myStations.map((station) => (
            <option key={station.id} value={station.id}>
              {station.name}
            </option>
          ))}
        </select>
        <select value={fuelType} onChange={(e) => setFuelType(e.target.value as FuelType)}>
          {Object.entries(FUEL_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <input
          type="number"
          step="1"
          placeholder="Литры"
          value={liters}
          onChange={(e) => setLiters(e.target.value)}
        />
        <button type="button" onClick={() => void handleSubmit()} disabled={busy || !liters}>
          {busy ? 'Заказываю...' : 'Заказать топливо'}
        </button>
      </div>
      {message && <p style={{ fontSize: 12, color: 'var(--text)' }}>{message}</p>}
      {error && (
        <p role="alert" style={{ fontSize: 12, color: 'crimson' }}>
          {error}
        </p>
      )}
    </div>
  )
}

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

  const { data: transactions } = useQuery({
    queryKey: ['transactions', gameId],
    queryFn: () => listMyTransactions(gameId ?? ''),
    enabled: Boolean(gameId),
  })

  const { data: refineries } = useQuery({
    queryKey: ['refineries', gameId],
    queryFn: () => listGameRefineries(gameId ?? ''),
    enabled: Boolean(gameId),
  })

  const { data: fuelOrders } = useQuery({
    queryKey: ['fuelOrders', gameId],
    queryFn: () => listFuelOrders(gameId ?? ''),
    enabled: Boolean(gameId),
  })

  const myPlayerId = game?.players.find((p) => p.user_id === user?.id)?.id
  const ownsAnyStation = stations?.some((s) => s.owner_player_id === myPlayerId) ?? false
  const myStations = stations?.filter((s) => s.owner_player_id === myPlayerId) ?? []

  useGameSocket(gameId, (event) => {
    if (
      event.event === 'station.purchased' ||
      event.event === 'player.updated' ||
      event.event === 'station.price_changed'
    ) {
      void queryClient.invalidateQueries({ queryKey: ['gameStations', gameId] })
      void queryClient.invalidateQueries({ queryKey: ['game', gameId] })
    }
    if (event.event === 'economy.tick') {
      void queryClient.invalidateQueries({ queryKey: ['gameStations', gameId] })
      void queryClient.invalidateQueries({ queryKey: ['game', gameId] })
      void queryClient.invalidateQueries({ queryKey: ['transactions', gameId] })
    }
    if (event.event === 'fuel_order.created' || event.event === 'fuel_order.delivered') {
      void queryClient.invalidateQueries({ queryKey: ['fuelOrders', gameId] })
      void queryClient.invalidateQueries({ queryKey: ['gameStations', gameId] })
      void queryClient.invalidateQueries({ queryKey: ['refineries', gameId] })
      void queryClient.invalidateQueries({ queryKey: ['game', gameId] })
    }
  })

  function refreshAfterOrder(): void {
    void queryClient.invalidateQueries({ queryKey: ['fuelOrders', gameId] })
    void queryClient.invalidateQueries({ queryKey: ['refineries', gameId] })
    void queryClient.invalidateQueries({ queryKey: ['game', gameId] })
  }

  function refreshAfterPriceChange(): void {
    void queryClient.invalidateQueries({ queryKey: ['gameStations', gameId] })
  }

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
          {refineries?.map((refinery) => (
            <Marker
              key={refinery.id}
              position={[refinery.latitude, refinery.longitude]}
              icon={refineryIcon}
            >
              <Popup>
                <strong>{refinery.name}</strong>
                <br />
                {refinery.fuels.map((fuel) => (
                  <span key={fuel.fuel_type} style={{ display: 'block' }}>
                    {FUEL_LABELS[fuel.fuel_type]}: {fuel.current_liters} л по {fuel.purchase_price}{' '}
                    ₽/л
                  </span>
                ))}
                {gameId && (
                  <RefineryOrderForm
                    gameId={gameId}
                    refineryId={refinery.id}
                    myStations={myStations}
                    onOrdered={refreshAfterOrder}
                  />
                )}
              </Popup>
            </Marker>
          ))}
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
                      {gameId && (
                        <StationPriceEditor
                          gameId={gameId}
                          station={station}
                          onSaved={refreshAfterPriceChange}
                        />
                      )}
                    </>
                  )}
                </Popup>
              </Marker>
            )
          })}
        </MapContainer>
      </div>

      {gameId && ownsAnyStation && (
        <NetworkPriceEditor gameId={gameId} onSaved={refreshAfterPriceChange} />
      )}

      {fuelOrders && <FuelOrdersPanel orders={fuelOrders} stations={stations ?? []} />}

      {transactions && <IncomeChart transactions={transactions} />}
    </main>
  )
}
