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
