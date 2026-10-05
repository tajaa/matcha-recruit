import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { CappePublicPlan, CappePublicPricing } from '../../types'
import Pricing from './Pricing'
import { allInPlan } from './shared'

function plan(overrides: Partial<CappePublicPlan>): CappePublicPlan {
  return {
    code: 'plan',
    name: 'Plan',
    description: null,
    sort_order: 0,
    platform_fee_bps: 0,
    allowed_fulfillment: [],
    site_limit: null,
    mailbox_quota_included: 0,
    prices: [],
    intro_price_cents: null,
    intro_days: null,
    ...overrides,
  }
}

const month = (cents: number) => ({ interval: 'month', unit_amount_cents: cents, currency: 'USD', purchasable: true })
const year = (cents: number) => ({ interval: 'year', unit_amount_cents: cents, currency: 'USD', purchasable: true })

const catalog: CappePublicPricing = {
  plans: [
    plan({ code: 'business', name: 'Business', sort_order: 2, platform_fee_bps: 150, allowed_fulfillment: ['physical', 'digital', 'service', 'booking'], prices: [month(4900), year(49000)], intro_price_cents: 100, intro_days: 30 }),
    plan({ code: 'free', name: 'Free', sort_order: 0, platform_fee_bps: 200, allowed_fulfillment: ['physical', 'digital', 'service', 'booking'], site_limit: 1 }),
    plan({ code: 'creator', name: 'Creator', sort_order: 1, platform_fee_bps: 300, allowed_fulfillment: ['service', 'booking'], prices: [month(1900)] }),
  ],
  addons: [{ code: 'mailbox', name: 'Private email', description: null, unit_label: 'mailbox', prices: [month(300)] }],
}

function renderPricing(state: Parameters<typeof Pricing>[0]['pricing']) {
  return render(<MemoryRouter><Pricing pricing={state} /></MemoryRouter>)
}

describe('landing Pricing', () => {
  it('renders live plans in catalog order with their real prices and fees', () => {
    renderPricing({ status: 'ready', pricing: catalog })
    const cards = screen.getAllByRole('article')
    expect(cards.map((c) => c.getAttribute('data-testid'))).toEqual(['plan-free', 'plan-creator', 'plan-business'])
    const business = within(screen.getByTestId('plan-business'))
    expect(business.getByText('$49')).toBeTruthy()
    expect(business.getByText('1.5% fee per sale')).toBeTruthy()
    expect(within(screen.getByTestId('plan-free')).getByText('$0')).toBeTruthy()
    expect(screen.getByText(/Private email: \$3\/mailbox\/mo/)).toBeTruthy()
  })

  it('shows the intro badge only on plans whose intro is live', () => {
    renderPricing({ status: 'ready', pricing: catalog })
    expect(within(screen.getByTestId('plan-business')).getByText('$1 for your first 30 days')).toBeTruthy()
    expect(within(screen.getByTestId('plan-creator')).queryByText(/first \d+ days/)).toBeNull()
  })

  it('switches to yearly prices, falling back to monthly where no yearly price exists', () => {
    renderPricing({ status: 'ready', pricing: catalog })
    fireEvent.click(screen.getByRole('button', { name: 'Yearly' }))
    expect(within(screen.getByTestId('plan-business')).getByText('$490')).toBeTruthy()
    expect(within(screen.getByTestId('plan-creator')).getByText('$19')).toBeTruthy()
  })

  it('carries the picked plan and the interval on show into signup', () => {
    renderPricing({ status: 'ready', pricing: catalog })
    const cta = (code: string) => within(screen.getByTestId(`plan-${code}`)).getByRole('link').getAttribute('href')

    expect(cta('free')).toBe('/gummfit/website-setup')
    expect(cta('business')).toBe('/gummfit/website-setup?plan=business&interval=month')

    fireEvent.click(screen.getByRole('button', { name: /yearly/i }))
    expect(cta('business')).toBe('/gummfit/website-setup?plan=business&interval=year')
    // Creator has no yearly price, so it is quoted (and bought) monthly.
    expect(cta('creator')).toBe('/gummfit/website-setup?plan=creator&interval=month')
  })

  it('hides the whole section when the catalog cannot load', () => {
    const { container } = renderPricing({ status: 'error' })
    expect(container.querySelector('#pricing')).toBeNull()
  })
})

describe('featured plan', () => {
  it('selects the cheapest paid plan that covers every fulfillment type', () => {
    expect(allInPlan(catalog.plans)?.code).toBe('business')
  })
})
