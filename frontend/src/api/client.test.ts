import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, clearToken, errorMessage, getToken, safeNext, setToken } from './client'

const assign = vi.fn()
const store = new Map<string, string>()

function respond(status: number, body: unknown) {
  const fetchMock = vi.fn(async (..._args: unknown[]) => new Response(status === 204 ? null : JSON.stringify(body), { status }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

beforeEach(() => {
  store.clear()
  assign.mockClear()
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => store.set(k, v),
    removeItem: (k: string) => store.delete(k),
  })
  vi.stubGlobal('window', { location: { pathname: '/orders/5/bom', search: '?a=1', assign } })
})

describe('api', () => {
  it('attaches the bearer token and drops empty query params', async () => {
    setToken('abc')
    const fetchMock = respond(200, [])
    await api('/orders', { query: { needs_bom: true, q: '', limit: 10, skip: null } })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/orders?needs_bom=true&limit=10')
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer abc')
  })

  it('sends no Authorization header when signed out', async () => {
    const fetchMock = respond(200, {})
    await api('/auth/me')
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init.headers).toEqual({})
  })

  it('posts JSON bodies and form bodies correctly', async () => {
    const fetchMock = respond(200, {})
    await api('/boms/preview', { json: { order_id: 1 } })
    await api('/auth/login', { form: { username: 'a', password: 'b' } })
    const [, jsonInit] = fetchMock.mock.calls[0] as [string, RequestInit]
    const [, formInit] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(jsonInit.method).toBe('POST')
    expect(jsonInit.body).toBe('{"order_id":1}')
    expect(formInit.method).toBe('POST')
    expect(String(formInit.body)).toBe('username=a&password=b')
  })

  it('on 401 clears the token and redirects to login, keeping the current page', async () => {
    setToken('expired')
    respond(401, { detail: 'Session expired, sign in again' })
    await expect(api('/orders')).rejects.toBeInstanceOf(ApiError)
    expect(getToken()).toBeNull()
    expect(assign).toHaveBeenCalledWith('/login?next=%2Forders%2F5%2Fbom%3Fa%3D1')
  })

  it('does not redirect on a login 401 (wrong password)', async () => {
    respond(401, { detail: 'Wrong email or password' })
    await expect(api('/auth/login', { form: {}, skipAuthRedirect: true })).rejects.toThrow('Wrong email or password')
    expect(assign).not.toHaveBeenCalled()
  })

  it('does not redirect-loop when already on /login', async () => {
    vi.stubGlobal('window', { location: { pathname: '/login', search: '', assign } })
    respond(401, { detail: 'Not signed in' })
    await expect(api('/auth/me')).rejects.toBeInstanceOf(ApiError)
    expect(assign).not.toHaveBeenCalled()
  })

  it('returns undefined for 204', async () => {
    respond(204, null)
    await expect(api('/auth/password', { json: {} })).resolves.toBeUndefined()
  })

  it('survives a non-JSON error body', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('Bad Gateway', { status: 502 })))
    await expect(api('/orders')).rejects.toThrow('Request failed (502)')
  })
})

describe('error messages', () => {
  it('reads string details', () => {
    expect(new ApiError(400, 'No template').message).toBe('No template')
  })

  it('reads FastAPI validation lists', () => {
    expect(new ApiError(422, [{ msg: 'field required' }, { msg: 'bad type' }]).message).toBe('field required; bad type')
  })

  it('reads the save-blocked object, including which lines failed', () => {
    const detail = { message: 'A formula has a problem; fix the template first', lines: [['SS Metal', 'Unknown input “X”']] }
    expect(new ApiError(422, detail).message).toBe('A formula has a problem; fix the template first — SS Metal: Unknown input “X”')
  })

  it('explains network failures', () => {
    expect(errorMessage(new TypeError('Failed to fetch'))).toMatch(/reach the server/)
  })
})

describe('safeNext', () => {
  it.each([
    ['/orders/5/bom', '/orders/5/bom'],
    [null, '/'],
    ['', '/'],
    ['https://evil.example', '/'],
    ['//evil.example', '/'],
    ['/\\evil.example', '/'],
  ])('%s -> %s', (input, expected) => {
    expect(safeNext(input)).toBe(expected)
  })
})

it('clearToken removes the token', () => {
  setToken('x')
  clearToken()
  expect(getToken()).toBeNull()
})
