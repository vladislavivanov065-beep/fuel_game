import { apiRequest } from './client'

export interface FinancialTransaction {
  id: string
  transaction_type: string
  amount: string
  balance_before: string
  balance_after: string
  reference_type: string | null
  created_at: string
}

export function listMyTransactions(gameId: string): Promise<FinancialTransaction[]> {
  return apiRequest<FinancialTransaction[]>(`/api/games/${gameId}/me/transactions`)
}
