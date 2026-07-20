import { useEffect, useState } from 'react'
import type { FuelOrder } from '../api/fuelOrders'
import type { GameStation } from '../api/gameStations'
import { Card } from './ui/Card'

const STATUS_LABELS: Record<string, string> = {
  created: 'Создан',
  paid: 'Оплачен',
  loading: 'Загрузка',
  in_transit: 'В пути',
  partially_delivered: 'Частично доставлен',
  delivered: 'Доставлен',
  cancelled: 'Отменён',
  failed: 'Ошибка',
}

function formatCountdown(completedAt: string | null, now: number): string {
  if (!completedAt) return '—'
  const remainingMs = new Date(completedAt).getTime() - now
  if (remainingMs <= 0) return 'прибывает...'
  const totalSeconds = Math.ceil(remainingMs / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export function FuelOrdersPanel({
  orders,
  stations,
}: {
  orders: FuelOrder[]
  stations: GameStation[]
}) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(interval)
  }, [])

  if (orders.length === 0) {
    return null
  }

  const stationNameById = new Map(stations.map((s) => [s.id, s.name]))

  return (
    <Card style={{ marginBottom: 16 }}>
      <h3 style={{ margin: '0 0 8px', fontSize: 16 }}>Заказы топлива</h3>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left', padding: 4 }}>Станция</th>
            <th style={{ textAlign: 'left', padding: 4 }}>Топливо</th>
            <th style={{ textAlign: 'right', padding: 4 }}>Литры</th>
            <th style={{ textAlign: 'right', padding: 4 }}>Стоимость</th>
            <th style={{ textAlign: 'left', padding: 4 }}>Статус</th>
            <th style={{ textAlign: 'right', padding: 4 }}>Прибытие через</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) =>
            order.stops.map((stop, index) => (
              <tr key={`${order.id}-${index}`}>
                <td style={{ padding: 4 }}>{stationNameById.get(stop.station_id) ?? '—'}</td>
                <td style={{ padding: 4 }}>{stop.fuel_type}</td>
                <td style={{ padding: 4, textAlign: 'right' }}>{stop.liters}</td>
                <td style={{ padding: 4, textAlign: 'right' }}>{order.total_cost}</td>
                <td style={{ padding: 4 }}>{STATUS_LABELS[order.status] ?? order.status}</td>
                <td style={{ padding: 4, textAlign: 'right' }}>
                  {order.status === 'in_transit'
                    ? formatCountdown(order.completed_at, now)
                    : '—'}
                </td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </Card>
  )
}
