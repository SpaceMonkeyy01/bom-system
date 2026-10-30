import { api } from '../api/client'
import type { Order } from '../api/types'

export type OrderScope = 'needs_bom' | 'all'

// High because done orders are filtered out here, after the API's limit (API_REQUESTS.md #1).
const ORDER_LIMIT = 2000

/**
 * Shared by the queue and the dashboard's count, so the two can't disagree.
 * An order done in Airtable doesn't need a BOM here, even with none saved in this app: nearly all of them were
 * costed in the old sheet.
 */
export const ordersQuery = (scope: OrderScope, q = '') => ({
  queryKey: ['orders', { scope, q }],
  queryFn: async ({ signal }: { signal: AbortSignal }) => {
    const rows = await api<Order[]>('/orders', {
      query: { needs_bom: scope === 'needs_bom' ? true : undefined, q, limit: ORDER_LIMIT },
      signal,
    })
    return scope === 'needs_bom' ? rows.filter((o) => !o.airtable_bom_done) : rows
  },
})
