import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError } from '../api/client'
import type { GameStation } from '../api/gameStations'
import {
  acceptTradeOffer,
  cancelTradeOffer,
  createFuelSaleOffer,
  createStationSaleOffer,
  listTradeOffers,
  rejectTradeOffer,
  type FuelSaleTerms,
  type StationSaleTerms,
  type TradeOffer,
  type TradeOfferType,
} from '../api/trades'
import { Card } from './ui/Card'

const FUEL_LABELS: Record<string, string> = {
  ai92: 'АИ-92',
  ai95: 'АИ-95',
  diesel: 'Дизель',
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'ожидает',
  accepted: 'принято',
  rejected: 'отклонено',
  cancelled: 'отменено',
  expired: 'истекло',
}

function isStationSaleTerms(
  offerType: TradeOfferType,
  terms: unknown,
): terms is StationSaleTerms {
  return offerType === 'station_sale' && typeof terms === 'object' && terms !== null
}

function isFuelSaleTerms(offerType: TradeOfferType, terms: unknown): terms is FuelSaleTerms {
  return offerType === 'fuel_sale' && typeof terms === 'object' && terms !== null
}

function describeOffer(offer: TradeOffer): string {
  if (isStationSaleTerms(offer.offer_type, offer.terms)) {
    return `Продажа АЗС за ${offer.terms.price} ₽`
  }
  if (isFuelSaleTerms(offer.offer_type, offer.terms)) {
    return `Продажа ${offer.terms.liters} л ${FUEL_LABELS[offer.terms.fuel_type] ?? offer.terms.fuel_type} по ${offer.terms.price_per_liter} ₽/л`
  }
  return 'Сделка'
}

interface OtherPlayer {
  userId: string
  displayName: string
}

export function TradesPanel({
  gameId,
  myPlayerId,
  myUserId,
  myStations,
  otherPlayers,
}: {
  gameId: string
  myPlayerId: string | undefined
  myUserId: string | undefined
  myStations: GameStation[]
  otherPlayers: OtherPlayer[]
}) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const [offerType, setOfferType] = useState<TradeOfferType>('station_sale')
  const [stationId, setStationId] = useState('')
  const [price, setPrice] = useState('')
  const [fuelType, setFuelType] = useState<'ai92' | 'ai95' | 'diesel'>('ai92')
  const [liters, setLiters] = useState('')
  const [pricePerLiter, setPricePerLiter] = useState('')
  const [buyerUserId, setBuyerUserId] = useState('')
  const [acceptStationByTrade, setAcceptStationByTrade] = useState<Record<string, string>>({})

  const { data: offers } = useQuery({
    queryKey: ['trades', gameId],
    queryFn: () => listTradeOffers(gameId),
    refetchInterval: 5000,
  })

  function invalidate(): Promise<unknown> {
    return Promise.all([
      queryClient.invalidateQueries({ queryKey: ['trades', gameId] }),
      queryClient.invalidateQueries({ queryKey: ['gameStations', gameId] }),
      queryClient.invalidateQueries({ queryKey: ['game', gameId] }),
      queryClient.invalidateQueries({ queryKey: ['transactions', gameId] }),
    ])
  }

  async function handleCreate(): Promise<void> {
    if (!stationId) return
    setBusyId('create')
    setError(null)
    try {
      if (offerType === 'station_sale') {
        if (!price) return
        await createStationSaleOffer(gameId, {
          stationId,
          price,
          buyerUserId: buyerUserId || undefined,
        })
      } else {
        if (!liters || !pricePerLiter) return
        await createFuelSaleOffer(gameId, {
          stationId,
          fuelType,
          liters,
          pricePerLiter,
          buyerUserId: buyerUserId || undefined,
        })
      }
      setPrice('')
      setLiters('')
      setPricePerLiter('')
      await invalidate()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create trade offer')
    } finally {
      setBusyId(null)
    }
  }

  async function handleAccept(offer: TradeOffer): Promise<void> {
    setBusyId(offer.id)
    setError(null)
    try {
      const buyerStationId = isFuelSaleTerms(offer.offer_type, offer.terms)
        ? acceptStationByTrade[offer.id]
        : undefined
      await acceptTradeOffer(gameId, offer.id, buyerStationId)
      await invalidate()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to accept trade offer')
    } finally {
      setBusyId(null)
    }
  }

  async function handleReject(offer: TradeOffer): Promise<void> {
    setBusyId(offer.id)
    setError(null)
    try {
      await rejectTradeOffer(gameId, offer.id)
      await invalidate()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to reject trade offer')
    } finally {
      setBusyId(null)
    }
  }

  async function handleCancel(offer: TradeOffer): Promise<void> {
    setBusyId(offer.id)
    setError(null)
    try {
      await cancelTradeOffer(gameId, offer.id)
      await invalidate()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to cancel trade offer')
    } finally {
      setBusyId(null)
    }
  }

  const pendingOffers = (offers ?? []).filter((o) => o.status === 'pending')
  const historyOffers = (offers ?? []).filter((o) => o.status !== 'pending')

  return (
    <Card style={{ marginBottom: 16 }}>
      <h3 style={{ margin: '0 0 8px', fontSize: 16 }}>Сделки</h3>
      {error && (
        <p role="alert" style={{ color: 'crimson', fontSize: 12 }}>
          {error}
        </p>
      )}

      {pendingOffers.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
          {pendingOffers.map((offer) => {
            const isSeller = offer.seller_id === myPlayerId
            const isTargetedBuyer = offer.buyer_id === myPlayerId
            const isOpenOffer = offer.buyer_id === null
            const canAccept = !isSeller && (isTargetedBuyer || isOpenOffer)
            const canReject = isTargetedBuyer
            const canCancel = isSeller
            const needsBuyerStation = isFuelSaleTerms(offer.offer_type, offer.terms)

            return (
              <li key={offer.id} style={{ marginBottom: 6 }}>
                {describeOffer(offer)}
                {' — '}
                {STATUS_LABELS[offer.status]}
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 2 }}>
                  {canAccept && needsBuyerStation && (
                    <select
                      value={acceptStationByTrade[offer.id] ?? ''}
                      onChange={(e) =>
                        setAcceptStationByTrade((s) => ({ ...s, [offer.id]: e.target.value }))
                      }
                    >
                      <option value="">Куда принять топливо?</option>
                      {myStations.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                    </select>
                  )}
                  {canAccept && (
                    <button
                      type="button"
                      onClick={() => void handleAccept(offer)}
                      disabled={
                        busyId === offer.id ||
                        (needsBuyerStation && !acceptStationByTrade[offer.id])
                      }
                    >
                      Принять
                    </button>
                  )}
                  {canReject && (
                    <button
                      type="button"
                      onClick={() => void handleReject(offer)}
                      disabled={busyId === offer.id}
                    >
                      Отклонить
                    </button>
                  )}
                  {canCancel && (
                    <button
                      type="button"
                      onClick={() => void handleCancel(offer)}
                      disabled={busyId === offer.id}
                    >
                      Отменить
                    </button>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      ) : (
        <p style={{ fontSize: 12 }}>Нет активных сделок.</p>
      )}

      <div style={{ marginTop: 12, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
        <h4 style={{ margin: '0 0 6px', fontSize: 13 }}>Новое предложение</h4>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
          <select
            value={offerType}
            onChange={(e) => setOfferType(e.target.value as TradeOfferType)}
          >
            <option value="station_sale">Продать АЗС</option>
            <option value="fuel_sale">Продать топливо</option>
          </select>
          <select value={stationId} onChange={(e) => setStationId(e.target.value)}>
            <option value="">Выберите станцию</option>
            {myStations.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          {offerType === 'station_sale' ? (
            <input
              type="number"
              step="0.01"
              placeholder="Цена"
              style={{ width: 100 }}
              value={price}
              onChange={(e) => setPrice(e.target.value)}
            />
          ) : (
            <>
              <select
                value={fuelType}
                onChange={(e) => setFuelType(e.target.value as 'ai92' | 'ai95' | 'diesel')}
              >
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
                style={{ width: 80 }}
                value={liters}
                onChange={(e) => setLiters(e.target.value)}
              />
              <input
                type="number"
                step="0.01"
                placeholder="Цена/л"
                style={{ width: 80 }}
                value={pricePerLiter}
                onChange={(e) => setPricePerLiter(e.target.value)}
              />
            </>
          )}
          <select value={buyerUserId} onChange={(e) => setBuyerUserId(e.target.value)}>
            <option value="">Любой игрок</option>
            {otherPlayers
              .filter((p) => p.userId !== myUserId)
              .map((p) => (
                <option key={p.userId} value={p.userId}>
                  {p.displayName}
                </option>
              ))}
          </select>
          <button
            type="button"
            onClick={() => void handleCreate()}
            disabled={busyId === 'create' || !stationId}
          >
            {busyId === 'create' ? 'Создаю...' : 'Создать'}
          </button>
        </div>
      </div>

      {historyOffers.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ fontSize: 12, cursor: 'pointer' }}>История сделок</summary>
          <ul style={{ margin: '4px 0 0', paddingLeft: 18, fontSize: 12 }}>
            {historyOffers.map((offer) => (
              <li key={offer.id}>
                {describeOffer(offer)} — {STATUS_LABELS[offer.status]}
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  )
}
