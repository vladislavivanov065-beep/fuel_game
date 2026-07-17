import { apiRequest } from './client'

export type TradeOfferType = 'station_sale' | 'fuel_sale'
export type TradeOfferStatus = 'pending' | 'accepted' | 'rejected' | 'cancelled' | 'expired'

export interface StationSaleTerms {
  station_id: string
  price: string
}

export interface FuelSaleTerms {
  station_id: string
  fuel_type: 'ai92' | 'ai95' | 'diesel'
  liters: string
  price_per_liter: string
}

export interface TradeOffer {
  id: string
  game_id: string
  seller_id: string
  buyer_id: string | null
  offer_type: TradeOfferType
  status: TradeOfferStatus
  terms: StationSaleTerms | FuelSaleTerms | Record<string, unknown>
  expires_at: string
  created_at: string
}

export function listTradeOffers(gameId: string): Promise<TradeOffer[]> {
  return apiRequest<TradeOffer[]>(`/api/games/${gameId}/trades`)
}

export function createStationSaleOffer(
  gameId: string,
  params: { stationId: string; price: string; buyerUserId?: string; expiresInMinutes?: number },
): Promise<TradeOffer> {
  return apiRequest<TradeOffer>(`/api/games/${gameId}/trades`, {
    method: 'POST',
    body: JSON.stringify({
      offer_type: 'station_sale',
      terms: { station_id: params.stationId, price: params.price },
      buyer_user_id: params.buyerUserId ?? null,
      expires_in_minutes: params.expiresInMinutes ?? 60,
    }),
  })
}

export function createFuelSaleOffer(
  gameId: string,
  params: {
    stationId: string
    fuelType: 'ai92' | 'ai95' | 'diesel'
    liters: string
    pricePerLiter: string
    buyerUserId?: string
    expiresInMinutes?: number
  },
): Promise<TradeOffer> {
  return apiRequest<TradeOffer>(`/api/games/${gameId}/trades`, {
    method: 'POST',
    body: JSON.stringify({
      offer_type: 'fuel_sale',
      terms: {
        station_id: params.stationId,
        fuel_type: params.fuelType,
        liters: params.liters,
        price_per_liter: params.pricePerLiter,
      },
      buyer_user_id: params.buyerUserId ?? null,
      expires_in_minutes: params.expiresInMinutes ?? 60,
    }),
  })
}

export function acceptTradeOffer(
  gameId: string,
  tradeId: string,
  buyerStationId?: string,
): Promise<TradeOffer> {
  return apiRequest<TradeOffer>(`/api/games/${gameId}/trades/${tradeId}/accept`, {
    method: 'POST',
    body: JSON.stringify({ buyer_station_id: buyerStationId ?? null }),
  })
}

export function rejectTradeOffer(gameId: string, tradeId: string): Promise<TradeOffer> {
  return apiRequest<TradeOffer>(`/api/games/${gameId}/trades/${tradeId}/reject`, {
    method: 'POST',
  })
}

export function cancelTradeOffer(gameId: string, tradeId: string): Promise<TradeOffer> {
  return apiRequest<TradeOffer>(`/api/games/${gameId}/trades/${tradeId}/cancel`, {
    method: 'POST',
  })
}

export function counterTradeOffer(
  gameId: string,
  tradeId: string,
  terms: StationSaleTerms | FuelSaleTerms,
  expiresInMinutes?: number,
): Promise<TradeOffer> {
  return apiRequest<TradeOffer>(`/api/games/${gameId}/trades/${tradeId}/counter`, {
    method: 'POST',
    body: JSON.stringify({ terms, expires_in_minutes: expiresInMinutes ?? 60 }),
  })
}
