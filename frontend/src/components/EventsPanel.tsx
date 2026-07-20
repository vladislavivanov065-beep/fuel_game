import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { type EventType, listActiveEvents, listEventHistory, triggerEvent } from '../api/events'

const EVENT_LABELS: Record<EventType, string> = {
  storm: 'Гроза',
  severe_storm: 'Сильный шторм',
  fuel_riot: 'Топливный бунт',
  economic_crisis: 'Экономический кризис',
  oil_price_drop: 'Падение цен на нефть',
  road_works: 'Дорожные работы',
  city_festival: 'Городской фестиваль',
  tourist_season: 'Туристический сезон',
  regulatory_inspection: 'Проверка контролирующих органов',
  refinery_breakdown: 'Поломка на НПЗ',
  police_checkpoint: 'Перекрытие ГАИ',
}

export function EventsPanel({ gameId, isAdmin }: { gameId: string; isAdmin: boolean }) {
  const queryClient = useQueryClient()
  const [now, setNow] = useState(() => Date.now())
  const [selectedType, setSelectedType] = useState<EventType>('storm')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(interval)
  }, [])

  const { data: activeEvents } = useQuery({
    queryKey: ['events', gameId],
    queryFn: () => listActiveEvents(gameId),
    refetchInterval: 5000,
  })
  const { data: history } = useQuery({
    queryKey: ['eventHistory', gameId],
    queryFn: () => listEventHistory(gameId),
    refetchInterval: 15000,
  })

  async function handleTrigger(): Promise<void> {
    setBusy(true)
    setError(null)
    try {
      await triggerEvent(gameId, selectedType)
      await queryClient.invalidateQueries({ queryKey: ['events', gameId] })
      await queryClient.invalidateQueries({ queryKey: ['eventHistory', gameId] })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to trigger event')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 16, marginBottom: 16 }}
    >
      <h3 style={{ margin: '0 0 8px', fontSize: 16 }}>События</h3>
      {activeEvents && activeEvents.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {activeEvents.map((event) => {
            const remainingMs = new Date(event.ends_at).getTime() - now
            const remainingSeconds = Math.max(0, Math.ceil(remainingMs / 1000))
            return (
              <li key={event.id}>
                {EVENT_LABELS[event.event_type]} — осталось {remainingSeconds} с
              </li>
            )
          })}
        </ul>
      ) : (
        <p style={{ fontSize: 12 }}>Нет активных событий.</p>
      )}

      {isAdmin && (
        <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value as EventType)}
          >
            {Object.entries(EVENT_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <button type="button" onClick={() => void handleTrigger()} disabled={busy}>
            {busy ? 'Запуск...' : 'Запустить событие'}
          </button>
        </div>
      )}
      {error && (
        <p role="alert" style={{ color: 'crimson', fontSize: 12 }}>
          {error}
        </p>
      )}

      {history && history.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ fontSize: 12, cursor: 'pointer' }}>История событий</summary>
          <ul style={{ margin: '4px 0 0', paddingLeft: 18, fontSize: 12 }}>
            {history.map((event) => (
              <li key={event.id}>
                {EVENT_LABELS[event.event_type]} —{' '}
                {event.status === 'active' ? 'активно' : 'завершено'}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
