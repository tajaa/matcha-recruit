import { afterEach, describe, it, expect, vi } from 'vitest'
import { clearAuthTokens, setAuthTokens } from './authStorage'
import { API_BASE, ApiError, api, logoutSession, planRequiredMessage, _shouldReportStatus } from './client'
import { authLoginPath } from './authPaths'

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
  it('returns Gummfit staff to their login when refresh is rejected after a 401', async () => {
    const location = { pathname: '/gummfit/admin/models', search: '', hash: '', href: '' }
    vi.stubGlobal('location', location)
    setAuthTokens(tokenWithExpiry(Date.now() / 1000 - 60), 'refresh-token')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })))

    await expect(api.get('/auth/me')).rejects.toThrow('Session expired')
    await vi.waitFor(() => expect(location.href).toBe('/gummfit/admin/login?next=%2Fgummfit%2Fadmin%2Fmodels'))
  })

  it.each(['/gummfit/admin/login', '/gummfit/admin/login/', '/GUMMFIT/ADMIN/LOGIN', '/gummfit/%61dmin/%6cogin/'])('does not redirect repeatedly from staff login %s', async (pathname) => {
    const location = { pathname, search: '', hash: '', href: '' }
    vi.stubGlobal('location', location)
    await logoutSession()
    expect(location.href).toBe('')
  })

  it('keeps expiry at an encoded staff destination in the staff realm', async () => {
    const location = { pathname: '/gummfit/%61dmin/models', search: '?tab=default', hash: '', href: '' }
    vi.stubGlobal('location', location)
    await logoutSession()
    expect(location.href).toBe('/gummfit/admin/login?next=%2Fgummfit%2F%2561dmin%2Fmodels%3Ftab%3Ddefault')
  })

  it('returns Gummfit staff to their login with their destination after revoking the session', async () => {
    const location = { pathname: '/gummfit/admin', search: '?view=bank', hash: '', href: '' }
    vi.stubGlobal('location', location)
    setAuthTokens(tokenWithExpiry(Date.now() / 1000 + 60), '')
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(logoutSession()).resolves.toBe(true)

    expect(location.href).toBe('/gummfit/admin/login?next=%2Fgummfit%2Fadmin%3Fview%3Dbank')
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE}/auth/logout`, expect.objectContaining({ method: 'POST' }))
  })

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

describe('authLoginPath', () => {
  it.each(['/admin', '/app/settings', '/gummfit/creators', '/gummfit/administrator'])('preserves the Matcha login for %s', (path) => {
    expect(authLoginPath(path)).toBe('/login')
  })
})

describe('planRequiredMessage', () => {
  it('turns the structured 403 detail into a readable sentence', () => {
    expect(planRequiredMessage({ code: 'plan_required', required_plan: 'lite', current_plan: 'free', feature: 'journals_full' }))
      .toBe('This needs the Lite plan.')
    expect(planRequiredMessage({ code: 'plan_required', required_plan: 'pro', current_plan: 'lite', feature: 'go_live' }))
      .toBe('This needs the Pro plan.')
  })
})
