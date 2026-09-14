import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { useMeMock } = vi.hoisted(() => ({ useMeMock: vi.fn() }))

vi.mock('../../hooks/useMe', () => ({ useMe: useMeMock }))

import RequireScOnboardingComplete from './RequireScOnboardingComplete'

function renderGuard() {
  return render(
    <MemoryRouter initialEntries={['/app']}>
      <Routes>
        <Route path="/app" element={<RequireScOnboardingComplete><div>Product home</div></RequireScOnboardingComplete>} />
        <Route path="/sc/onboarding" element={<div>S&amp;C wizard</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

function meProfile(overrides: Record<string, unknown> = {}) {
  return {
    user: { role: 'client' },
    profile: {
      signup_source: 'product:safety-co',
      enabled_features: { employees: true },
      product: {
        features: ['employees'],
        gate_feature: 'employees',
        pricing_model: 'per_seat',
        onboarding_kind: 'sc',
      },
      sc_onboarding_completed_at: null,
      ...overrides,
    },
  }
}

describe('RequireScOnboardingComplete', () => {
  beforeEach(() => vi.clearAllMocks())

  it('routes an activated, incomplete S&C company admin into setup', () => {
    useMeMock.mockReturnValue({ me: meProfile(), loading: false })
    renderGuard()
    expect(screen.getByText('S&C wizard')).toBeInTheDocument()
  })

  it('admits the company after setup is complete', () => {
    useMeMock.mockReturnValue({
      me: meProfile({ sc_onboarding_completed_at: '2026-09-14T00:00:00Z' }),
      loading: false,
    })
    renderGuard()
    expect(screen.getByText('Product home')).toBeInTheDocument()
  })

  it('does not reroute a product that is still awaiting activation', () => {
    useMeMock.mockReturnValue({ me: meProfile({ enabled_features: { employees: false } }), loading: false })
    renderGuard()
    expect(screen.getByText('Product home')).toBeInTheDocument()
  })

  it('does not change routing for a non-S&C account', () => {
    useMeMock.mockReturnValue({
      me: { user: { role: 'client' }, profile: { signup_source: 'matcha_lite', enabled_features: {} } },
      loading: false,
    })
    renderGuard()
    expect(screen.getByText('Product home')).toBeInTheDocument()
  })
})
