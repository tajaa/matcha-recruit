import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest'
import { CAPPE_NETWORK_ERROR, CappeApiError, cappeApi, cappePublicGet, cappePublicPost, setCappeTokens, clearCappeTokens, getCappeToken } from './api'

/** Regression guard for the storage migration: several call sites in this file
 * (including `request`, the helper behind every Cappe screen) kept reading the
 * access token out of localStorage after the tokens moved to sessionStorage.
 * localStorage is purged at module load, so those reads always returned null
 * and every request went out unauthenticated. */
describe('cappe api auth header', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })
  afterEach(() => { vi.restoreAllMocks() })

  it('attaches the tab-session token to requests', async () => {
    setCappeTokens('cappe-access', 'cappe-refresh')
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200, json: async () => ({}),
    })
    vi.stubGlobal('fetch', fetchMock)

    await cappeApi.get('/sites')

    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer cappe-access')
    clearCappeTokens()
  })

  it('sends no auth header once the session is cleared', async () => {
    setCappeTokens('cappe-access', 'cappe-refresh')
    clearCappeTokens()
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200, json: async () => ({}),
    })
    vi.stubGlobal('fetch', fetchMock)

    await cappeApi.get('/sites')

    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>
    expect(headers.Authorization).toBeUndefined()
  })
})

/** A 401 sends `request()` through the refresh path, and what happens next
 *  depends entirely on WHY the refresh failed. The editor can be holding an
 *  unsaved page at that moment, so the two outcomes must not be conflated:
 *  the server rejecting the refresh token ends the session, a fetch that never
 *  reached the server does not. */
describe('cappe api refresh outcomes', () => {
  const originalLocation = window.location

  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    // jsdom's window.location is not writable and an assignment to .href
    // throws "Not implemented: navigation" — swap in a plain object so the
    // redirect is observable instead.
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { pathname: '/cappe/sites/abc/pages/def', href: '' },
    })
  })
  afterEach(() => {
    vi.restoreAllMocks()
    Object.defineProperty(window, 'location', { configurable: true, writable: true, value: originalLocation })
  })

  it('logs out and redirects when the refresh token is rejected', async () => {
    setCappeTokens('stale-access', 'stale-refresh')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) })   // the request
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) })   // /auth/refresh
    vi.stubGlobal('fetch', fetchMock)

    await expect(cappeApi.get('/sites')).rejects.toThrow('Session expired')

    expect(getCappeToken()).toBeNull()
    expect(window.location.href).toBe('/cappe/login')
  })

  it('keeps the session when the refresh fetch never reaches the server', async () => {
    setCappeTokens('good-access', 'good-refresh')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) })   // the request
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))                     // /auth/refresh
    vi.stubGlobal('fetch', fetchMock)

    await expect(cappeApi.get('/sites')).rejects.toThrow(CAPPE_NETWORK_ERROR)

    // The whole point: tokens survive, so nothing the user was editing is lost.
    expect(getCappeToken()).toBe('good-access')
    expect(window.location.href).toBe('')
  })

  it('treats a 5xx from /auth/refresh as transport, not a dead session', async () => {
    setCappeTokens('good-access', 'good-refresh')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) })
      .mockResolvedValueOnce({ ok: false, status: 502, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)

    await expect(cappeApi.get('/sites')).rejects.toThrow(CAPPE_NETWORK_ERROR)
    expect(getCappeToken()).toBe('good-access')
  })

  it('retries the original request once the refresh succeeds', async () => {
    setCappeTokens('stale-access', 'good-refresh')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) })
      .mockResolvedValueOnce({
        ok: true, status: 200,
        json: async () => ({ access_token: 'fresh-access', refresh_token: 'fresh-refresh' }),
      })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ok: 1 }) })
    vi.stubGlobal('fetch', fetchMock)

    await expect(cappeApi.get('/sites')).resolves.toEqual({ ok: 1 })

    expect(getCappeToken()).toBe('fresh-access')
    const retryHeaders = fetchMock.mock.calls[2][1].headers as Record<string, string>
    expect(retryHeaders.Authorization).toBe('Bearer fresh-access')
  })

  it('sends a creator session to the creator login, not the business one', async () => {
    window.location.pathname = '/gummfit/creators/dashboard/earnings'
    setCappeTokens('stale-access', 'stale-refresh')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) })
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)

    await expect(cappeApi.get('/creators/me/earnings')).rejects.toThrow('Session expired')
    expect(window.location.href).toBe('/gummfit/creators/login')
  })

  it('sends a brand session to the brand login', async () => {
    window.location.pathname = '/gummfit/creators/brands/dashboard/collabs'
    setCappeTokens('stale-access', 'stale-refresh')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) })
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)

    await expect(cappeApi.get('/collab/offers')).rejects.toThrow('Session expired')
    expect(window.location.href).toBe('/gummfit/creators/brands/login')
  })

  it('does not redirect when already sitting on a login page', async () => {
    window.location.pathname = '/cappe/login'
    setCappeTokens('stale-access', 'stale-refresh')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) })
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)

    await expect(cappeApi.get('/auth/me')).rejects.toThrow('Session expired')
    expect(window.location.href).toBe('')
  })
})

/** Signup and login show `err.message` straight on the form, so what a failed
 *  response turns into is user-facing copy. */
describe('cappe api error shape', () => {
  afterEach(() => { vi.restoreAllMocks() })

  function failWith(status: number, body: unknown) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status, statusText: 'Nope', json: async () => body,
    }))
  }

  it('turns a FastAPI validation list into readable field messages', async () => {
    failWith(422, { detail: [
      { type: 'value_error', loc: ['body', 'email'], msg: 'value is not a valid email address' },
      { type: 'string_too_short', loc: ['body', 'intended_plan'], msg: 'Value error, too short' },
    ] })
    const err = await cappePublicPost('/auth/signup', {}).catch((e: CappeApiError) => e) as CappeApiError
    expect(err).toBeInstanceOf(CappeApiError)
    expect(err.message).toBe('Email: value is not a valid email address Intended plan: too short')
    expect(err.code).toBe('validation')
    expect(err.status).toBe(422)
  })

  it('keeps the code and status of a structured detail', async () => {
    failWith(403, { detail: { code: 'email_unverified', message: 'Please confirm your email.' } })
    const err = await cappePublicPost('/auth/login', {}).catch((e: CappeApiError) => e) as CappeApiError
    expect(err.message).toBe('Please confirm your email.')
    expect(err.code).toBe('email_unverified')
    expect(err.status).toBe(403)
  })

  it('carries the status of a plain-string detail', async () => {
    failWith(429, { detail: 'Too many requests' })
    const err = await cappePublicGet('/public/pricing').catch((e: CappeApiError) => e) as CappeApiError
    expect(err.message).toBe('Too many requests')
    expect(err.status).toBe(429)
  })

  it('falls back to generic copy when the body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 502, statusText: 'Bad Gateway', json: async () => { throw new Error('html') },
    }))
    const err = await cappeApi.get('/sites').catch((e: CappeApiError) => e) as CappeApiError
    expect(err.message).toBe('Server error — try again in a moment.')
  })

  it('never shows an empty validation message', async () => {
    failWith(422, { detail: [{}] })
    const err = await cappePublicPost('/auth/signup', {}).catch((e: CappeApiError) => e) as CappeApiError
    expect(err.message).toMatch(/isn’t valid/)
  })
})
