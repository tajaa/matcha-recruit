import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest'
import { cappeApi, setCappeTokens, clearCappeTokens } from './api'

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
