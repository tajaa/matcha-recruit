import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { api, PLAN_REQUIRED_EVENT } from '../../api/client'
import { useEntitlements } from './useEntitlements'

const mock = vi.hoisted(() => ({
  userId: 'free-user',
  getEntitlements: vi.fn(),
}))

vi.mock('../../hooks/useMe', () => ({
  useMe: () => ({ me: { user: { id: mock.userId } } }),
}))
vi.mock('../api/matchaWork/entitlements', () => ({
  getEntitlements: mock.getEntitlements,
}))

const entitlement = (plan: 'free' | 'lite' | 'pro' | 'business', journalsFull: boolean) => ({
  plan,
  features: { journals_full: journalsFull },
  quotas: { token_limit: 25_000, window_hours: 12 },
})

beforeEach(() => {
  mock.getEntitlements.mockReset()
})

describe('useEntitlements', () => {
  it('keeps gates open while loading, then uses the server feature flags', async () => {
    mock.userId = 'free-user'
    let resolve: (value: ReturnType<typeof entitlement>) => void = () => {}
    mock.getEntitlements.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const free = renderHook(() => useEntitlements())
    expect(free.result.current.can('journals_full')).toBe(true)
    resolve(entitlement('free', false))
    await waitFor(() => expect(free.result.current.can('journals_full')).toBe(false))
    free.unmount()

    mock.userId = 'lite-user'
    mock.getEntitlements.mockResolvedValueOnce(entitlement('lite', true))
    const lite = renderHook(() => useEntitlements())
    await waitFor(() => expect(lite.result.current.can('journals_full')).toBe(true))
    expect(lite.result.current.plan).toBe('lite')
  })

  it('treats Business as Pro rank and retains the last plan after a fetch error', async () => {
    mock.userId = 'business-user'
    mock.getEntitlements.mockResolvedValueOnce(entitlement('business', true))
    const { result } = renderHook(() => useEntitlements())
    await waitFor(() => expect(result.current.plan).toBe('business'))
    expect(result.current.atLeast('pro')).toBe(true)
    mock.getEntitlements.mockRejectedValueOnce(new Error('offline'))
    await result.current.refetch()
    expect(result.current.plan).toBe('business')
  })

  it('shares one in-flight request across hook consumers', async () => {
    mock.userId = 'shared-user'
    mock.getEntitlements.mockResolvedValue(entitlement('pro', true))
    const first = renderHook(() => useEntitlements())
    const second = renderHook(() => useEntitlements())
    await waitFor(() => expect(first.result.current.plan).toBe('pro'))
    expect(second.result.current.plan).toBe('pro')
    expect(mock.getEntitlements).toHaveBeenCalledTimes(1)
  })

  it('publishes the structured 403 detail for the paywall', async () => {
    const detail = {
      code: 'plan_required',
      required_plan: 'pro',
      current_plan: 'free',
      feature: 'projects_collab',
    }
    const onPaywall = vi.fn()
    window.addEventListener(PLAN_REQUIRED_EVENT, onPaywall)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), {
      status: 403,
      headers: { 'Content-Type': 'application/json' },
    })))
    try {
      await expect(api.get('/matcha-work/projects')).rejects.toMatchObject({ status: 403 })
      expect(onPaywall).toHaveBeenCalledTimes(1)
      expect((onPaywall.mock.calls[0][0] as CustomEvent).detail).toEqual(detail)
    } finally {
      window.removeEventListener(PLAN_REQUIRED_EVENT, onPaywall)
      vi.unstubAllGlobals()
    }
  })
})
