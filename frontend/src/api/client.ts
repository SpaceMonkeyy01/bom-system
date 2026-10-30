/** Small typed wrapper over fetch: bearer token from localStorage, redirect to /login on 401. */

const TOKEN_KEY = 'bom_access_token'
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (token: string) => localStorage.setItem(TOKEN_KEY, token)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(detailMessage(status, detail))
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/** FastAPI errors: a string, a list of validation errors, or our {message, lines | input_errors} objects. */
function detailMessage(status: number, detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msgs = detail.map((d) => (d as { msg?: unknown }).msg).filter((m) => typeof m === 'string')
    if (msgs.length) return msgs.join('; ')
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const { message, lines } = detail as { message: unknown; lines?: unknown }
    const parts = [String(message)]
    if (Array.isArray(lines)) parts.push(...lines.map((l) => (Array.isArray(l) ? l.join(': ') : String(l))))
    return parts.join(' — ')
  }
  return `Request failed (${status})`
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof TypeError) return 'Can’t reach the server. Check that the API is running.'
  return error instanceof Error ? error.message : 'Something went wrong'
}

/** Only ever send people back to a path on this site, so a crafted ?next= can't redirect them elsewhere. */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.includes('\\')) return '/'
  return next
}

/** Returns false when already on /login, so the caller can report the error instead. */
function redirectToLogin(): boolean {
  const { pathname, search } = window.location
  if (pathname === '/login') return false
  window.location.assign(`/login?next=${encodeURIComponent(pathname + search)}`)
  return true
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  query?: Record<string, string | number | boolean | null | undefined>
  json?: unknown
  form?: Record<string, string>
  signal?: AbortSignal
  /** Set for the login call, where a 401 means "wrong password", not "session expired". */
  skipAuthRedirect?: boolean
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method, query, json, form, signal, skipAuthRedirect } = options
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  }
  const qs = params.toString()

  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let body: BodyInit | undefined
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(json)
  } else if (form) {
    body = new URLSearchParams(form)
  }

  const res = await fetch(`${API_BASE}/api${path}${qs ? `?${qs}` : ''}`, {
    method: method ?? (body ? 'POST' : 'GET'),
    headers,
    body,
    signal,
  })

  if (res.status === 401 && !skipAuthRedirect) {
    clearToken()
    // The page is about to unload: stay pending so nothing re-renders into an error or a second redirect.
    if (redirectToLogin()) return new Promise<T>(() => {})
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    throw new ApiError(res.status, data?.detail ?? null)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}
