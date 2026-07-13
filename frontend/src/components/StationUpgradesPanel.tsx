import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError } from '../api/client'
import {
  listStationUpgrades,
  purchaseStationUpgrade,
  type UpgradeType,
} from '../api/stationUpgrades'

const UPGRADE_LABELS: Record<UpgradeType, string> = {
  pumps: 'Доп. колонки',
  tanks: 'Резервуары',
  shop: 'Магазин',
  food_court: 'Фудкорт',
  car_wash: 'Автомойка',
  rating: 'Рейтинг',
  advertising: 'Реклама',
  parking: 'Парковка',
  loyalty_program: 'Программа лояльности',
}

const STATUS_LABELS: Record<string, string> = {
  under_construction: 'строится',
  active: 'активно',
  expired: 'истекло',
}

export function StationUpgradesPanel({
  gameId,
  stationId,
}: {
  gameId: string
  stationId: string
}) {
  const queryClient = useQueryClient()
  const [busyType, setBusyType] = useState<UpgradeType | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data: upgrades } = useQuery({
    queryKey: ['stationUpgrades', gameId, stationId],
    queryFn: () => listStationUpgrades(gameId, stationId),
  })

  async function handlePurchase(upgradeType: UpgradeType): Promise<void> {
    setBusyType(upgradeType)
    setError(null)
    try {
      await purchaseStationUpgrade(gameId, stationId, upgradeType)
      await queryClient.invalidateQueries({
        queryKey: ['stationUpgrades', gameId, stationId],
      })
      await queryClient.invalidateQueries({ queryKey: ['game', gameId] })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to purchase upgrade')
    } finally {
      setBusyType(null)
    }
  }

  if (!upgrades) return null

  return (
    <div style={{ marginTop: 8 }}>
      <h4 style={{ margin: '4px 0', fontSize: 13 }}>Улучшения</h4>
      {error && (
        <p role="alert" style={{ color: 'crimson', fontSize: 12 }}>
          {error}
        </p>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {upgrades.map((upgrade) => (
          <div
            key={upgrade.upgrade_type}
            style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}
          >
            <span style={{ minWidth: 130 }}>{UPGRADE_LABELS[upgrade.upgrade_type]}</span>
            <span>ур. {upgrade.level}</span>
            {upgrade.status && (
              <span style={{ color: 'var(--text-secondary, #666)' }}>
                ({STATUS_LABELS[upgrade.status] ?? upgrade.status})
              </span>
            )}
            <button
              type="button"
              onClick={() => void handlePurchase(upgrade.upgrade_type)}
              disabled={busyType === upgrade.upgrade_type}
            >
              {busyType === upgrade.upgrade_type
                ? '...'
                : `Улучшить (${upgrade.next_level_cost} ₽)`}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
