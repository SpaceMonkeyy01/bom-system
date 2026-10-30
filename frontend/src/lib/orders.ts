import { api } from '../api/client'
import type { Order, SignType } from '../api/types'
import type { Tone } from '../theme'
import { isOverdue } from './format'

export type OrderScope = 'needs_bom' | 'all'

// High because done orders are filtered out here, after the API's limit (API_REQUESTS.md #1).
const ORDER_LIMIT = 2000

/**
 * Shared by the queue, the sidebar count and the hero numbers, so they can't disagree.
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

export interface OrderStatus {
  tone: Tone
  word: string
}

const todayIso = (today: Date) => `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`

/** Status pill, first in every row: the one thing to know about the order. */
export function orderStatus(order: Pick<Order, 'bom_count' | 'dispatch_by' | 'airtable_bom_done' | 'status'>, today: Date = new Date()): OrderStatus {
  if (order.bom_count > 0) return { tone: 'done', word: 'BOM saved' }
  if (order.airtable_bom_done) return { tone: 'neutral', word: 'Done in sheet' }
  if (isOverdue(order.dispatch_by, today)) return { tone: 'missing', word: 'Overdue' }
  if (order.dispatch_by?.slice(0, 10) === todayIso(today)) return { tone: 'pending', word: 'Due today' }
  return { tone: 'neutral', word: 'Needs BOM' }
}

/** Why this order can't be costed yet, if it can't: no sign type, or one with nothing published. */
export function templateProblem(order: Pick<Order, 'sign_type_id' | 'sign_type_raw'>, signTypes: SignType[] | undefined): string | null {
  if (order.sign_type_id === null) return order.sign_type_raw ? `Unmapped: “${order.sign_type_raw}”` : 'No sign type'
  if (!signTypes) return null
  const st = signTypes.find((s) => s.id === order.sign_type_id)
  return st && st.published_template_id === null ? 'No published template' : null
}
