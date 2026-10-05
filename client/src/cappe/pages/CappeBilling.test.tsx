import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CappeBillingPlan, CappeSubscription } from '../types'
import CappeBilling, { POLL_MS, POLL_TRIES } from './CappeBilling'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const refresh = vi.hoisted(() => vi.fn())
vi.mock('../api', () => ({ cappeApi: api }))
vi.mock('../hooks/useCappeMe', () => ({
  useCappeMe: () => ({ account: { plan: 'free', account_type: 'business' }, refresh }),
}))

function plan(overrides: Partial<CappeBillingPlan>): CappeBillingPlan {
  return {
    code: 'plan', name: 'Plan', description: null, sort_order: 0, platform_fee_bps: 0,
    allowed_fulfillment: [], site_limit: null, mailbox_quota_included: 0, prices: [],
    intro_price_cents: null, intro_days: null, status: 'active', can_sell: true,
    ...overrides,
  }
}
const price = (interval: string, cents: number) => ({ interval, unit_amount_cents: cents, currency: 'USD', purchasable: true })

const PLANS = [
  plan({ code: 'free', name: 'Free', site_limit: 1, platform_fee_bps: 200 }),
  plan({ code: 'creator', name: 'Creator', prices: [price('month', 1900)] }),
  plan({ code: 'business', name: 'Business', prices: [price('month', 4900), price('year', 49000)], intro_price_cents: 100, intro_days: 30 }),
]

function subscription(overrides: Partial<CappeSubscription> = {}): CappeSubscription {
  return {
    plan_code: 'business', plan_name: 'Business', interval: 'month', status: 'active', source: 'stripe',
    current_period_end: '2026-11-04T00:00:00Z', trial_end: null, cancel_at_period_end: false, comped_until: null,
    ...overrides,
  }
}

/** Serve the catalog, and a queue of subscription answers (last one repeats). */
function serve(...subs: (CappeSubscription | null)[]) {
  const queue = [...subs]
  api.get.mockImplementation(async (path: string) => {
    if (path === '/billing/catalog') return { plans: PLANS, intro_available: true }
    return queue.length > 1 ? queue.shift() : queue[0]
  })
}

function Search() {
  return <p data-testid="search">{useLocation().search}</p>
}

function open(search = '') {
  render(
    <MemoryRouter initialEntries={[`/cappe/billing${search}`]}>
      <Routes>
        <Route path="/cappe/billing" element={<><CappeBilling /><Search /></>} />
      </Routes>
    </MemoryRouter>,
  )
}

/** Let every look of the payment poll run: one tick per render. */
async function exhaustPoll() {
  for (let tick = 0; tick <= POLL_TRIES; tick += 1) {
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS) })
  }
}

const assign = vi.fn()
const originalLocation = window.location

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
  refresh.mockReset()
  assign.mockReset()
  Object.defineProperty(window, 'location', {
    configurable: true, value: { origin: 'https://gummfit.example', assign },
  })
})
afterEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation })
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('CappeBilling', () => {
  it('shows the lineup and the current plan for a free account', async () => {
    serve(null)
    open()

    expect(await screen.findByText(/Current plan:/)).toHaveTextContent('Current plan: Free')
    expect(screen.getByTestId('billing-plan-free')).toHaveTextContent('Current plan')
    expect(screen.getByTestId('billing-plan-business')).toHaveTextContent('$49')
    expect(screen.getByTestId('billing-plan-business')).toHaveTextContent('$1 for your first 30 days')
    // Nothing to manage until there is a subscription.
    expect(screen.queryByRole('button', { name: 'Manage billing' })).toBeNull()
  })

  it('goes straight to checkout for a plan picked at signup, once', async () => {
    serve(null)
    api.post.mockResolvedValue({ checkout_url: 'https://checkout.stripe.test/c/1' })
    open('?start=business&interval=year')

    await waitFor(() => expect(assign).toHaveBeenCalledWith('https://checkout.stripe.test/c/1'))
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post).toHaveBeenCalledWith('/billing/checkout', {
      plan_code: 'business',
      interval: 'year',
      success_url: 'https://gummfit.example/cappe/billing?checkout=success',
      cancel_url: 'https://gummfit.example/cappe/billing?checkout=cancelled',
    })
    // A reload must not start checkout again.
    expect(screen.getByTestId('search')).toBeEmptyDOMElement()
  })

  it('falls back to monthly when the picked plan has no yearly price', async () => {
    serve(null)
    api.post.mockResolvedValue({ checkout_url: 'https://checkout.stripe.test/c/2' })
    open('?start=creator&interval=year')

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post.mock.calls[0][1]).toMatchObject({ plan_code: 'creator', interval: 'month' })
  })

  it('does not start a second subscription for someone who already has one', async () => {
    serve(subscription())
    open('?start=creator')

    expect(await screen.findByText(/already have a subscription/)).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('explains an unknown plan instead of redirecting nowhere', async () => {
    serve(null)
    open('?start=enterprise')
    expect(await screen.findByText(/isn’t available right now/)).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('keeps the person on the page when checkout cannot start', async () => {
    serve(null)
    api.post.mockRejectedValue(new Error('Billing is not configured for this plan yet.'))
    open()
    fireEvent.click(await screen.findByRole('button', { name: 'Choose Creator' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Billing is not configured for this plan yet.')
    expect(assign).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Choose Creator' })).toBeEnabled()
  })

  it('waits for the plan to update after a paid checkout, then refreshes the account', async () => {
    vi.useFakeTimers()
    // The webhook has not landed for the first two looks.
    serve(null, null, subscription({ status: 'trialing', trial_end: '2026-11-04T00:00:00Z' }))
    open('?checkout=success')

    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(screen.getByText('Confirming your payment…')).toBeInTheDocument()

    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS * 3) })
    expect(screen.getByText(/You’re on the Business plan/)).toBeInTheDocument()
    expect(screen.getByText(/Current plan:/)).toHaveTextContent('Current plan: Business')
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('search')).toBeEmptyDOMElement()
  })

  it('says the plan is still updating when the webhook is slow, and can check again', async () => {
    vi.useFakeTimers()
    serve(null)
    open('?checkout=success')

    await exhaustPoll()
    expect(screen.getByText(/hasn’t updated yet/)).toBeInTheDocument()
    expect(refresh).not.toHaveBeenCalled()

    serve(subscription())
    fireEvent.click(screen.getByRole('button', { name: 'Check again' }))
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(screen.getByText(/You’re on the Business plan/)).toBeInTheDocument()
  })

  it('does not claim a payment on the ambiguous fallback return', async () => {
    vi.useFakeTimers()
    serve(null)
    open('?checkout=return')

    await exhaustPoll()
    expect(screen.queryByText(/payment went through/)).toBeNull()
    expect(screen.getByText(/If you completed checkout/)).toBeInTheDocument()
  })

  it('confirms nothing was charged after a cancelled checkout', async () => {
    serve(null)
    open('?checkout=cancelled')
    expect(await screen.findByText('Checkout cancelled. Nothing was charged.')).toBeInTheDocument()
    expect(screen.getByTestId('search')).toBeEmptyDOMElement()
  })

  it('switches plan only after the charge is confirmed by the person', async () => {
    serve(subscription({ plan_code: 'creator', plan_name: 'Creator' }))
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    api.post.mockResolvedValue(subscription())
    open()

    const upgrade = await screen.findByRole('button', { name: 'Switch to Business' })
    fireEvent.click(upgrade)
    expect(confirm.mock.calls[0][0]).toMatch(/\$49\/month/)
    expect(api.post).not.toHaveBeenCalled()

    fireEvent.click(upgrade)
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/billing/change-plan', { plan_code: 'business', interval: 'month' }))
    expect(await screen.findByText('You’re now on Business.')).toBeInTheDocument()
    expect(refresh).toHaveBeenCalled()
    // Free is reached by cancelling in Stripe, not by a button here.
    expect(screen.getByTestId('billing-plan-free')).toHaveTextContent('cancel under “Manage billing”')
  })

  it('opens the Stripe portal and comes back to this page', async () => {
    serve(subscription())
    api.post.mockResolvedValue({ portal_url: 'https://billing.stripe.test/p/1' })
    open()
    fireEvent.click(await screen.findByRole('button', { name: 'Manage billing' }))

    await waitFor(() => expect(assign).toHaveBeenCalledWith('https://billing.stripe.test/p/1'))
    expect(api.post).toHaveBeenCalledWith('/billing/portal', { return_url: 'https://gummfit.example/cappe/billing' })
  })

  it('reports a billing page that cannot load', async () => {
    api.get.mockRejectedValue(new Error('Server error — try again in a moment.'))
    open()
    expect(await screen.findByRole('alert')).toHaveTextContent('Server error')
  })
})
