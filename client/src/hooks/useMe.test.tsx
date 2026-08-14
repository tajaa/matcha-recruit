import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../api/client', async () => {
  class ApiError extends Error {
    status: number
    body: unknown
    constructor(message: string, status: number, body?: unknown) {
      super(message)
      this.name = 'ApiError'
      this.status = status
      this.body = body
    }
  }
  return { ApiError, api: { get: vi.fn() } }
})

import { ApiError, api } from '../api/client'
import { useMe, invalidateMeCache } from './useMe'

const mockGet = vi.mocked(api.get)

// The distinction under test is load-bearing for route guards: AppLayout wraps
// the whole tenant surface and RequireRole wraps /admin and /broker. Both used
// to redirect on `!me`, which collapses "no session" into "the lookup failed" —
// so a single 502 on /auth/me logged the user out and discarded their location.
describe('useMe — authFailed distinguishes no-session from lookup-failure', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    invalidateMeCache()
  })

  it('sets authFailed on 401 (session genuinely gone)', async () => {
    mockGet.mockRejectedValue(new ApiError('Unauthorized', 401, null))
    const { result } = renderHook(() => useMe())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.me).toBeNull()
    expect(result.current.authFailed).toBe(true)
  })

  it('sets authFailed on 403', async () => {
    mockGet.mockRejectedValue(new ApiError('Forbidden', 403, null))
    const { result } = renderHook(() => useMe())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.authFailed).toBe(true)
  })

  it('does NOT set authFailed on a 502 — this is the forced-logout regression', async () => {
    mockGet.mockRejectedValue(new ApiError('Server unavailable', 502, null))
    const { result } = renderHook(() => useMe())
    await waitFor(() => expect(result.current.loading).toBe(false))
    // me is still null (we have no user), but the guards must not redirect.
    expect(result.current.me).toBeNull()
    expect(result.current.authFailed).toBe(false)
  })

  it('does NOT set authFailed on a network error with no status', async () => {
    mockGet.mockRejectedValue(new TypeError('Failed to fetch'))
    const { result } = renderHook(() => useMe())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.authFailed).toBe(false)
  })

  it('clears authFailed once a later load succeeds', async () => {
    mockGet.mockRejectedValueOnce(new ApiError('Unauthorized', 401, null))
    const { result } = renderHook(() => useMe())
    await waitFor(() => expect(result.current.authFailed).toBe(true))

    mockGet.mockResolvedValue({ user: { id: 'u1', role: 'client' }, profile: {} })
    await act(async () => { result.current.refresh() })
    await waitFor(() => expect(result.current.authFailed).toBe(false))
    expect(result.current.me).not.toBeNull()
  })

  it('reports no failure on a successful load', async () => {
    mockGet.mockResolvedValue({ user: { id: 'u1', role: 'client' }, profile: {} })
    const { result } = renderHook(() => useMe())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.authFailed).toBe(false)
    expect(result.current.me).not.toBeNull()
  })

  it('propagates a refreshed entitlement to every mounted consumer', async () => {
    const withoutOps = { user: { id: 'u1', role: 'client' }, profile: { enabled_features: { matcha_ops: false } } }
    const withOps = { user: { id: 'u1', role: 'client' }, profile: { enabled_features: { matcha_ops: true } } }
    mockGet.mockResolvedValueOnce(withoutOps)

    const first = renderHook(() => useMe())
    const second = renderHook(() => useMe())
    await waitFor(() => expect(first.result.current.loading).toBe(false))
    await waitFor(() => expect(second.result.current.loading).toBe(false))
    expect(first.result.current.hasFeature('matcha_ops')).toBe(false)
    expect(second.result.current.hasFeature('matcha_ops')).toBe(false)

    mockGet.mockResolvedValueOnce(withOps)
    await act(async () => { await first.result.current.refresh() })

    expect(first.result.current.hasFeature('matcha_ops')).toBe(true)
    expect(second.result.current.hasFeature('matcha_ops')).toBe(true)
    expect(mockGet).toHaveBeenCalledTimes(2)
  })
})
