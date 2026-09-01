import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// vi.mock is hoisted above the imports, so the fns must be created inside it.
vi.mock('./client', () => ({
  logoutSession: vi.fn().mockResolvedValue(true),
  ensureFreshToken: vi.fn().mockResolvedValue('token'),
}))

import { setAuthTokens, clearAuthTokens, recordActivity } from './authStorage'
import { installSessionSecurity } from './sessionSecurity'
import { ensureFreshToken, logoutSession } from './client'

const mockLogout = vi.mocked(logoutSession)
const mockRefresh = vi.mocked(ensureFreshToken)

describe('installSessionSecurity', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    sessionStorage.clear()
    mockLogout.mockClear()
    mockRefresh.mockClear()
  })
  afterEach(() => { vi.useRealTimers(); clearAuthTokens() })

  it('does not sign out a restored session that has no activity marker yet', () => {
    // A page RELOAD, faithfully: sessionStorage survives it, module memory does
    // not, and the shared localStorage marker may be gone (blocked, cleared, or
    // removed by a sibling tab's logout). Writing sessionStorage directly is
    // what makes this a reload rather than a login — setAuthTokens would seed
    // the in-memory stamp that a real reload has already lost.
    sessionStorage.setItem('matcha_access_token', 'access')
    sessionStorage.setItem('matcha_refresh_token', 'refresh')
    localStorage.removeItem('matcha_last_activity_at')
    const teardown = installSessionSecurity()
    expect(mockLogout).not.toHaveBeenCalled()
    teardown()
  })

  it('signs out once activity is older than the idle window', () => {
    setAuthTokens('access', 'refresh')
    recordActivity(Date.now() - 31 * 60 * 1000)
    const teardown = installSessionSecurity()
    expect(mockLogout).toHaveBeenCalledTimes(1)
    teardown()
  })

  it('keeps the server idle clock warm while the user is active', async () => {
    setAuthTokens('access', 'refresh')
    const teardown = installSessionSecurity()
    expect(mockRefresh).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(30_000)
    // Without this tick the server's clock tracks request traffic, not the
    // user, and an active-but-quiet tab ages out mid-edit.
    expect(mockRefresh).toHaveBeenCalled()
    expect(mockLogout).not.toHaveBeenCalled()
    teardown()
  })

  it('does not refresh once the user has gone idle', async () => {
    setAuthTokens('access', 'refresh')
    recordActivity(Date.now() - 31 * 60 * 1000)
    const teardown = installSessionSecurity()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(mockRefresh).not.toHaveBeenCalled()
    teardown()
  })
})
