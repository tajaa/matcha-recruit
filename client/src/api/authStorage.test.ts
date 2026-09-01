import { beforeEach, describe, expect, it } from 'vitest'
import { clearAuthTokens, getAccessToken, getRefreshToken, setAuthTokens } from './authStorage'

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
})
