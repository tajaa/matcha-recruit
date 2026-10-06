import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Orders from './Orders'
import type { CappeOrder } from '../../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), openBlob: vi.fn() }))
vi.mock('../../api', () => ({ cappeApi: api }))
vi.mock('../../components/StripeConnectCard', () => ({ default: () => null }))
vi.mock('../../components/ImageUpload', () => ({ default: () => null }))

function order(over: Partial<CappeOrder>): CappeOrder {
  return {
    id: 'o-1', site_id: 's-1', customer_email: 'buyer@example.com', customer_name: 'Buyer',
    status: 'paid', subtotal_cents: 4000, tax_cents: 0, shipping_cents: 0, total_cents: 4000,
    receipt_number: null, currency: 'USD', payment_ref: 'pi_123', note: null,
    requires_approval: false, approved_at: null, decline_reason: null, metadata: {},
    created_at: '2026-10-01T12:00:00Z', updated_at: '2026-10-01T12:00:00Z', items: [],
    ...over,
  }
}

async function renderOrders(orders: CappeOrder[]) {
  api.get.mockResolvedValue(orders)
  render(
    <MemoryRouter initialEntries={['/sites/s-1/orders']}>
      <Routes><Route path="/sites/:siteId/orders" element={<Orders />} /></Routes>
    </MemoryRouter>,
  )
  await screen.findByText('buyer@example.com')
}

function options(select: HTMLElement) {
  return within(select).getAllByRole('option').map((o) => o.textContent)
}

let confirmSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
  api.patch.mockReset()
  confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
})

describe('Orders — status changes follow the server rules', () => {
  it('offers a pending order only the moves the server allows', async () => {
    await renderOrders([order({ status: 'pending', payment_ref: null })])
    expect(options(screen.getByRole('combobox'))).toEqual(['Change status…', 'Mark paid', 'Cancel order'])
    // No refund for an order that never took money.
    expect(screen.queryByRole('button', { name: /Refund/ })).not.toBeInTheDocument()
  })

  it('never offers "refunded" as a plain status', async () => {
    await renderOrders([order({ status: 'paid' })])
    const labels = options(screen.getByRole('combobox'))
    expect(labels).toEqual(['Change status…', 'Mark fulfilled'])
    expect(labels.join(' ').toLowerCase()).not.toContain('refund')
  })

  it('shows a declined order as declined, with nothing to change', async () => {
    // It used to render in the dropdown as "pending": `declined` was not in the list.
    await renderOrders([order({ status: 'declined', payment_ref: null })])
    expect(screen.getByText('declined')).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('asks before marking an order paid by hand, and says what that means', async () => {
    api.patch.mockResolvedValue(order({ status: 'paid', payment_ref: null }))
    await renderOrders([order({ status: 'pending', payment_ref: null })])
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'paid' } })
    expect(confirmSpy.mock.calls[0][0]).toContain('money you collected yourself')
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/sites/s-1/orders/o-1', { status: 'paid' }))
  })

  it('does nothing when the owner backs out of a cancel', async () => {
    confirmSpy.mockReturnValue(false)
    await renderOrders([order({ status: 'pending', payment_ref: null })])
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'cancelled' } })
    expect(api.patch).not.toHaveBeenCalled()
  })

  it('shows the server reason when a change is refused', async () => {
    api.patch.mockRejectedValue(new Error('A paid order can\'t be moved to pending.'))
    await renderOrders([order({ status: 'paid' })])
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'fulfilled' } })
    expect(await screen.findByText("A paid order can't be moved to pending.")).toBeInTheDocument()
  })
})

describe('Orders — refund is an action, not a status', () => {
  it('refunds a card order through the refund endpoint after confirming the amount', async () => {
    api.post.mockResolvedValue(order({ status: 'refunded', refunded_cents: 4000 }))
    await renderOrders([order({ status: 'paid' })])
    fireEvent.click(screen.getByRole('button', { name: /Refund/ }))

    const question = confirmSpy.mock.calls[0][0] as string
    expect(question).toContain('$40.00')
    expect(question).toContain("customer's card")
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/orders/o-1/refund'))
    expect(await screen.findByText('refunded')).toBeInTheDocument()
    // Not the generic status PATCH, which no longer accepts it.
    expect(api.patch).not.toHaveBeenCalled()
  })

  it('tells the owner no money moves for an order paid outside Stripe', async () => {
    api.post.mockResolvedValue(order({ status: 'refunded', payment_ref: null }))
    await renderOrders([order({ status: 'fulfilled', payment_ref: null })])
    fireEvent.click(screen.getByRole('button', { name: /Refund/ }))
    const question = confirmSpy.mock.calls[0][0] as string
    expect(question).toContain("wasn't paid by card")
    expect(question).toContain('return $40.00 to the customer yourself')
  })

  it('sends nothing when the owner backs out', async () => {
    confirmSpy.mockReturnValue(false)
    await renderOrders([order({ status: 'paid' })])
    fireEvent.click(screen.getByRole('button', { name: /Refund/ }))
    expect(api.post).not.toHaveBeenCalled()
  })

  it('leaves the order as it was and says why when Stripe refuses', async () => {
    api.post.mockRejectedValue(new Error('Stripe did not accept the refund, so the order was left as is: insufficient funds'))
    await renderOrders([order({ status: 'paid' })])
    fireEvent.click(screen.getByRole('button', { name: /Refund/ }))
    expect(await screen.findByText(/order was left as is/)).toBeInTheDocument()
    expect(screen.getByText('paid')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Refund/ })).toBeEnabled()
  })

  it('does not offer the button on a subscription order (refunded from Stripe, synced back)', async () => {
    await renderOrders([order({ status: 'paid', subscription_id: 'sub-1', payment_ref: null })])
    expect(screen.queryByRole('button', { name: /Refund/ })).not.toBeInTheDocument()
  })
})

describe('Orders — what Stripe told us', () => {
  it('flags an open dispute beside the order', async () => {
    await renderOrders([order({ dispute_status: 'needs_response' })])
    expect(screen.getByText(/dispute: needs response/)).toBeInTheDocument()
  })

  it('shows a partial refund amount while the order stays paid', async () => {
    await renderOrders([order({ status: 'paid', refunded_cents: 1200 })])
    expect(screen.getByText('$12.00 refunded')).toBeInTheDocument()
    expect(screen.getByText('paid')).toBeInTheDocument()
  })
})
