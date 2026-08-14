import { act, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { useMeMock } = vi.hoisted(() => ({ useMeMock: vi.fn() }))

vi.mock('../../hooks/useMe', () => ({ useMe: useMeMock }))
vi.mock('./UpgradeUpsellCard', () => ({
  UpgradeUpsellCard: ({ title }: { title: string }) => <div>{title}</div>,
}))

import { FeatureGate } from './FeatureGate'

const refresh = vi.fn().mockResolvedValue(undefined)

describe('FeatureGate', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    refresh.mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('admits a platform admin when explicitly allowed', () => {
    useMeMock.mockReturnValue({
      me: { user: { role: 'admin' }, profile: null },
      hasFeature: () => false,
      loading: false,
      refresh,
    })

    render(<FeatureGate feature="matcha_ops" label="Matcha Ops" allowPlatformAdmin><div>Ops home</div></FeatureGate>)

    expect(screen.getByText('Ops home')).toBeInTheDocument()
    expect(refresh).not.toHaveBeenCalled()
  })

  it('admits an entitled client tenant', () => {
    useMeMock.mockReturnValue({
      me: { user: { role: 'client' }, profile: { enabled_features: { matcha_ops: true } } },
      hasFeature: (feature: string) => feature === 'matcha_ops',
      loading: false,
      refresh,
    })

    render(<FeatureGate feature="matcha_ops" label="Matcha Ops"><div>Ops home</div></FeatureGate>)

    expect(screen.getByText('Ops home')).toBeInTheDocument()
    expect(refresh).not.toHaveBeenCalled()
  })

  it('shows an upsell after one denied refresh', async () => {
    useMeMock.mockReturnValue({
      me: { user: { role: 'client' }, profile: { enabled_features: { matcha_ops: false } } },
      hasFeature: () => false,
      loading: false,
      refresh,
    })

    render(<FeatureGate feature="matcha_ops" label="Matcha Ops"><div>Ops home</div></FeatureGate>)

    await waitFor(() => expect(screen.getByText('Upgrade to unlock Matcha Ops')).toBeInTheDocument())
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('falls back to the upsell when entitlement refresh stalls', async () => {
    vi.useFakeTimers()
    refresh.mockReturnValue(new Promise<void>(() => {}))
    useMeMock.mockReturnValue({
      me: { user: { role: 'client' }, profile: { enabled_features: { matcha_ops: false } } },
      hasFeature: () => false,
      loading: false,
      refresh,
    })

    render(<FeatureGate feature="matcha_ops" label="Matcha Ops"><div>Ops home</div></FeatureGate>)

    expect(screen.getByRole('status')).toHaveTextContent('Checking access')
    await vi.waitFor(() => expect(refresh).toHaveBeenCalledTimes(1))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000)
    })

    expect(screen.getByText('Upgrade to unlock Matcha Ops')).toBeInTheDocument()
  })
})
