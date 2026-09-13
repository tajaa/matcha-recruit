import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { useMeMock } = vi.hoisted(() => ({ useMeMock: vi.fn() }))

vi.mock('../../hooks/useMe', () => ({ useMe: useMeMock }))

import TenantSidebar from './TenantSidebar'


describe('TenantSidebar custom-product checkout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('explains how to recover when a per-location tenant has no stored location count', () => {
    useMeMock.mockReturnValue({
      loading: false,
      me: {
        profile: {
          signup_source: 'product:safety-pro',
          headcount: 20,
          location_count: 0,
          enabled_features: { incidents: false },
          product: {
            slug: 'safety-pro',
            name: 'Safety Pro',
            description: '',
            features: ['incidents'],
            gate_feature: 'incidents',
            pricing_model: 'per_location',
            price_cents: 2500,
            block_size: null,
            min_headcount: 1,
            max_headcount: 300,
            nav: null,
          },
        },
      },
    })

    render(<TenantSidebar />)

    expect(screen.getByText(/Your location count is missing/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'contact us' })).toHaveAttribute(
      'href',
      'mailto:hello@matcha.work',
    )
    expect(screen.getByRole('button', { name: 'Subscribe' })).toBeDisabled()
  })
})
