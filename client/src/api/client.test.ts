import { afterEach, describe, it, expect, vi } from 'vitest'
import { clearAuthTokens, setAuthTokens } from './authStorage'
import { API_BASE, ApiError, logoutSession, _shouldReportStatus } from './client'

function tokenWithExpiry(exp: number): string {
  return `header.${btoa(JSON.stringify({ exp }))}.signature`
}

afterEach(() => {
  clearAuthTokens()
  vi.unstubAllGlobals()
})

describe('API_BASE', () => {
  it('never ends with a slash (a trailing-slash VITE_API_URL would otherwise double-slash every request)', () => {
    expect(API_BASE.endsWith('/')).toBe(false)
    expect(API_BASE.length).toBeGreaterThan(0)
  })
})

describe('ApiError', () => {
  it('exposes status and body for callers branching on status', () => {
    const e = new ApiError('too many', 429, { detail: 'too many' })
    expect(e.status).toBe(429)
    expect(e.body).toEqual({ detail: 'too many' })
    expect(e.name).toBe('ApiError')
  })
})

describe('_shouldReportStatus', () => {
  it('skips expected client-input/business-rule/auth statuses', () => {
    for (const status of [400, 401, 402, 403, 404, 409, 410, 422, 429]) {
      expect(_shouldReportStatus(status)).toBe(false)
    }
  })

  it('reports network failures, 5xx, and anything unexpected', () => {
    expect(_shouldReportStatus(0)).toBe(true)
    expect(_shouldReportStatus(500)).toBe(true)
    expect(_shouldReportStatus(502)).toBe(true)
    expect(_shouldReportStatus(418)).toBe(true)
  })
})

describe('logoutSession', () => {
  it('does not send an expired access token to logout after refresh is rejected', async () => {
    setAuthTokens(tokenWithExpiry(Date.now() / 1000 - 60), 'refresh-token')
    window.history.replaceState({}, '', '/login')
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 401 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(logoutSession()).resolves.toBe(false)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`${API_BASE}/auth/refresh`)
  })
})
