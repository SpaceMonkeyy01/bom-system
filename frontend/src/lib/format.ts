const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "2026-11-01" -> "1 Nov 2026". Parsed by hand: new Date() reads it as UTC and can land on the previous day. */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  if (!y || !m || !d) return iso
  return `${d} ${MONTHS[m - 1]} ${y}`
}

export function isOverdue(iso: string | null | undefined, today: Date = new Date()): boolean {
  if (!iso) return false
  const pad = (n: number) => String(n).padStart(2, '0')
  return iso.slice(0, 10) < `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`
}

const todayIso = (today: Date) => `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`

/** "2 days ago", "yesterday", "today", "tomorrow", "in 3 days": the dispatch date as the team says it. */
export function dispatchWords(iso: string | null | undefined, today: Date = new Date()): string {
  if (!iso) return ''
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  const [ty, tm, td] = todayIso(today).split('-').map(Number)
  const days = Math.round((Date.UTC(y, m - 1, d) - Date.UTC(ty, tm - 1, td)) / 86_400_000)
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  if (days === -1) return 'yesterday'
  if (days < 0) return `${-days} days ago`
  return `in ${days} days`
}

/** "ago" (in minutes/hours/days) for a timestamp, or null when unknown. */
export function agoWords(iso: string | null | undefined, now: Date = new Date()): string | null {
  if (!iso) return null
  const ms = now.getTime() - new Date(iso).getTime()
  if (!Number.isFinite(ms)) return null
  const min = Math.round(ms / 60_000)
  if (min < 1) return 'just now'
  if (min < 60) return `${min} min ago`
  const h = Math.round(min / 60)
  if (h < 24) return `${h} h ago`
  const d = Math.round(h / 24)
  return `${d} day${d === 1 ? '' : 's'} ago`
}

export function fmtNum(value: number | null | undefined, maxDecimals = 2, minDecimals = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toLocaleString('en-US', { minimumFractionDigits: minDecimals, maximumFractionDigits: maxDecimals })
}

export const fmtPkr = (value: number | null | undefined) => fmtNum(value, 0)
export const fmtUsd = (value: number | null | undefined) => (value === null || value === undefined ? '—' : `$${fmtNum(value, 2, 2)}`)

export function fmtSize(width: number | null | undefined, height: number | null | undefined): string {
  if (width === null || width === undefined || height === null || height === undefined) return '—'
  return `${fmtNum(width, 3)} × ${fmtNum(height, 3)}`
}
