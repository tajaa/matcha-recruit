import { beforeEach, describe, expect, it } from 'vitest'
import { clearAuthTokens, getAccessToken, getRefreshToken, readLastActivity, recordActivity, setAuthTokens } from './authStorage'

describe('authStorage', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('keeps bearer tokens in tab-scoped storage, never persistent storage', () => {
    setAuthTokens('access', 'refresh')
    expect(getAccessToken()).toBe('access')
    expect(getRefreshToken()).toBe('refresh')
    expect(localStorage.getItem('matcha_access_token')).toBeNull()
    expect(localStorage.getItem('matcha_refresh_token')).toBeNull()
  })

  it('clears both current and legacy token locations', () => {
    localStorage.setItem('matcha_access_token', 'legacy')
    localStorage.setItem('matcha_refresh_token', 'legacy-refresh')
    localStorage.setItem('channels_outbox_v1:user-1', '[{"content":"sensitive"}]')
    setAuthTokens('access', 'refresh')
    clearAuthTokens()
    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
    expect(localStorage.getItem('matcha_access_token')).toBeNull()
    expect(localStorage.getItem('matcha_refresh_token')).toBeNull()
    expect(localStorage.getItem('channels_outbox_v1:user-1')).toBeNull()
  })

  it('survives a Web Storage implementation that throws', () => {
    const realSet = Storage.prototype.setItem
    const realGet = Storage.prototype.getItem
    Storage.prototype.setItem = () => { throw new DOMException('blocked') }
    Storage.prototype.getItem = () => { throw new DOMException('blocked') }
    try {
      // Must not escape into the caller's catch and be reported as a bad login.
      expect(() => setAuthTokens('access', 'refresh')).not.toThrow()
      expect(getAccessToken()).toBe('access')
      expect(getRefreshToken()).toBe('refresh')
    } finally {
      Storage.prototype.setItem = realSet
      Storage.prototype.getItem = realGet
    }
    clearAuthTokens()
    expect(getAccessToken()).toBeNull()
  })

  it('does not let a sibling tab logout blank this tab\'s idle clock', () => {
    setAuthTokens('access', 'refresh')
    recordActivity(1_000_000)
    // A logout in another tab removes the shared localStorage marker.
    localStorage.removeItem('matcha_last_activity_at')
    expect(readLastActivity()).toBe(1_000_000)
  })

  it('reports no activity rather than a sliding token timestamp when unset', () => {
    clearAuthTokens()
    expect(readLastActivity()).toBe(0)
  })
})
