import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Orders from './Orders'
import type { CappeOrder, CappeOrderItem } from '../../types'

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

function line(over: Partial<CappeOrderItem> = {}): CappeOrderItem {
  return {
    id: 'i-1', product_id: 'p-1', title: 'Mug', unit_price_cents: 2000, quantity: 2,
    fulfillment: 'physical', intake_answers: {}, selected_options: [], deliverable_url: null,
    booking_id: null, ...over,
  }
}

async function renderOrders(orders: CappeOrder[]) {
  api.get.mockResolvedValue(orders)
  render(
    <MemoryRouter initialEntries={['/sites/s-1/orders']}>
      <Routes><Route path="/sites/:siteId/orders" element={<Orders />} /></Routes>
    </MemoryRouter>,
  )
  if (orders.length) await screen.findAllByText('buyer@example.com')
}

const statusMenu = () => screen.getByRole('combobox', { name: /Change status/ })

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
    expect(options(statusMenu())).toEqual(['Change status…', 'Mark paid', 'Cancel order'])
    // No refund for an order that never took money.
    expect(screen.queryByRole('button', { name: /Refund/ })).not.toBeInTheDocument()
  })

  it('never offers "refunded" as a plain status', async () => {
    await renderOrders([order({ status: 'paid' })])
    const labels = options(statusMenu())
    expect(labels).toEqual(['Change status…', 'Mark fulfilled'])
    expect(labels.join(' ').toLowerCase()).not.toContain('refund')
  })

  it('shows a declined order as declined, with nothing to change', async () => {
    // It used to render in the dropdown as "pending": `declined` was not in the list.
    await renderOrders([order({ status: 'declined', payment_ref: null })])
    expect(screen.getByText('declined')).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: /Change status/ })).not.toBeInTheDocument()
  })

  it('asks before marking an order paid by hand, and says what that means', async () => {
    api.patch.mockResolvedValue(order({ status: 'paid', payment_ref: null }))
    await renderOrders([order({ status: 'pending', payment_ref: null })])
    fireEvent.change(statusMenu(), { target: { value: 'paid' } })
    expect(confirmSpy.mock.calls[0][0]).toContain('money you collected yourself')
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/sites/s-1/orders/o-1', { status: 'paid' }))
  })

  it('does nothing when the owner backs out of a cancel', async () => {
    confirmSpy.mockReturnValue(false)
    await renderOrders([order({ status: 'pending', payment_ref: null })])
    fireEvent.change(statusMenu(), { target: { value: 'cancelled' } })
    expect(api.patch).not.toHaveBeenCalled()
  })

  it('shows the server reason when a change is refused', async () => {
    api.patch.mockRejectedValue(new Error('A paid order can\'t be moved to pending.'))
    await renderOrders([order({ status: 'paid' })])
    fireEvent.change(statusMenu(), { target: { value: 'fulfilled' } })
    expect(await screen.findByText("A paid order can't be moved to pending.")).toBeInTheDocument()
  })
})

describe('Orders — refund is an action, not a status', () => {
  it('refunds a card order through the refund endpoint after confirming the amount', async () => {
    api.post.mockResolvedValue(order({ status: 'refunded', refunded_cents: 4000 }))
    await renderOrders([order({ status: 'paid' })])
    fireEvent.click(screen.getByRole('button', { name: /Refund/ }))

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Refund $40.00?')).toBeInTheDocument()
    expect(dialog.textContent).toContain("customer's card")
    // Not yet fulfilled: the goods are still here, so they go back on the shelf.
    expect(within(dialog).getByRole('checkbox', { name: /back in stock/ })).toBeChecked()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Refund $40.00' }))

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/orders/o-1/refund', { restock: true }))
    expect(await screen.findByText('refunded')).toBeInTheDocument()
    // Not the generic status PATCH, which no longer accepts it.
    expect(api.patch).not.toHaveBeenCalled()
  })

  it('does not restock a fulfilled order unless the owner says the goods came back', async () => {
    api.post.mockResolvedValue(order({ status: 'refunded' }))
    await renderOrders([order({ status: 'fulfilled' })])
    fireEvent.click(screen.getByRole('button', { name: /Refund/ }))
    const dialog = screen.getByRole('dialog')
    const box = within(dialog).getByRole('checkbox', { name: /back in stock/ })
    expect(box).not.toBeChecked()
    expect(dialog.textContent).toContain('only if the goods were returned')
    fireEvent.click(box)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Refund $40.00' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/orders/o-1/refund', { restock: true }))
  })

  it('tells the owner no money moves for an order paid outside Stripe', async () => {
    api.post.mockResolvedValue(order({ status: 'refunded', payment_ref: null }))
    await renderOrders([order({ status: 'fulfilled', payment_ref: null })])
    fireEvent.click(screen.getByRole('button', { name: /Refund/ }))
    const dialog = screen.getByRole('dialog')
    expect(dialog.textContent).toContain("wasn't paid by card")
    expect(dialog.textContent).toContain('return $40.00 to the customer yourself')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Mark refunded' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/orders/o-1/refund', { restock: false }))
  })

  it('sends nothing when the owner backs out', async () => {
    await renderOrders([order({ status: 'paid' })])
    fireEvent.click(screen.getByRole('button', { name: /Refund/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Keep order' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('leaves the order as it was and says why when Stripe refuses', async () => {
    api.post.mockRejectedValue(new Error('Stripe did not accept the refund, so the order was left as is: insufficient funds'))
    await renderOrders([order({ status: 'paid' })])
    fireEvent.click(screen.getByRole('button', { name: /Refund/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Refund $40.00' }))
    expect(await screen.findByText(/order was left as is/)).toBeInTheDocument()
    expect(screen.getByText('paid')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Refund/ })).toBeEnabled()
  })

  it('refunds a renewal order that knows its payment like any card order', async () => {
    await renderOrders([order({ status: 'paid', subscription_id: 'sub-1', payment_ref: 'pi_renewal' })])
    expect(screen.getByRole('button', { name: /Refund/ })).toBeInTheDocument()
  })

  it('does not offer the button on an older subscription order with no payment recorded (refund it in Stripe)', async () => {
    await renderOrders([order({ status: 'paid', subscription_id: 'sub-1', payment_ref: null })])
    expect(screen.queryByRole('button', { name: /Refund/ })).not.toBeInTheDocument()
  })
})

describe('Orders — part refunds', () => {
  it('refunds part of an order and returns only the units chosen', async () => {
    await renderOrders([order({ status: 'paid' })])
    api.get.mockResolvedValueOnce(order({ status: 'paid', items: [line(), line({ id: 'i-2', title: 'Zine', fulfillment: 'digital', quantity: 1 })] }))
    api.post.mockResolvedValue(order({ status: 'paid', refunded_cents: 1250 }))
    fireEvent.click(screen.getByRole('button', { name: /Refund/ }))
    const dialog = screen.getByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Part of it' }))
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/sites/s-1/orders/o-1'))
    fireEvent.change(within(dialog).getByLabelText(/Amount/), { target: { value: '12.50' } })
    // Only shipped goods can go back on the shelf.
    const units = await within(dialog).findByLabelText('Units of Mug back in stock')
    expect(within(dialog).queryByLabelText('Units of Zine back in stock')).not.toBeInTheDocument()
    fireEvent.change(units, { target: { value: '1' } })
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: 'One arrived chipped' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Refund $12.50' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/orders/o-1/refund', {
      amount_cents: 1250, lines: [{ item_id: 'i-1', quantity: 1 }], reason: 'One arrived chipped',
    }))
    expect(await screen.findByText('$12.50 refunded')).toBeInTheDocument()
  })

  it('refuses more than is left, before asking the server', async () => {
    await renderOrders([order({ status: 'paid', refunded_cents: 3000, items: [line()] })])
    fireEvent.click(screen.getByRole('button', { name: /Refund/ }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Refund $10.00?')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Part of it' }))
    fireEvent.change(within(dialog).getByLabelText(/Amount/), { target: { value: '20' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Refund $20.00' }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent('At most $10.00 is left')
    expect(api.post).not.toHaveBeenCalled()
  })

  it('offers no refund once everything has been refunded', async () => {
    await renderOrders([order({ status: 'paid', refunded_cents: 4000 })])
    expect(screen.queryByRole('button', { name: /Refund/ })).not.toBeInTheDocument()
  })

  it('lists the refunds in the order', async () => {
    api.get.mockResolvedValueOnce([order({ status: 'paid', refunded_cents: 1200 })])
    render(
      <MemoryRouter initialEntries={['/sites/s-1/orders']}>
        <Routes><Route path="/sites/:siteId/orders" element={<Orders />} /></Routes>
      </MemoryRouter>,
    )
    await screen.findAllByText('buyer@example.com')
    api.get.mockResolvedValueOnce(order({ status: 'paid', refunded_cents: 1200, items: [line()], refunds: [{
      id: 'r-1', amount_cents: 1200, restock: false, lines: [], reason: 'Late delivery', status: 'succeeded',
      source: 'stripe', stripe_refund_id: 're_1', failure: null, created_at: '2026-10-02T12:00:00Z',
    }] }))
    fireEvent.click(screen.getByRole('button', { name: 'Show order details' }))
    expect(await screen.findByText(/Refunded in Stripe/)).toBeInTheDocument()
    expect(screen.getByText('Late delivery')).toBeInTheDocument()
    expect(screen.getAllByText('−$12.00')).toHaveLength(2)   // the totals' Refunded line, and the refund itself
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

describe('Orders — finding an order', () => {
  it('asks for one page at a time and loads the next on request', async () => {
    const first = Array.from({ length: 50 }, (_, i) => order({ id: `o-${i}`, customer_name: `Buyer ${i}` }))
    await renderOrders(first)
    expect(api.get).toHaveBeenCalledWith('/sites/s-1/orders?limit=50&offset=0')
    api.get.mockResolvedValueOnce([order({ id: 'o-50', customer_name: 'Buyer 50' }), order({ id: 'o-3' })])
    fireEvent.click(screen.getByRole('button', { name: 'Load more orders' }))
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/sites/s-1/orders?limit=50&offset=50'))
    expect(await screen.findByText('Buyer 50')).toBeInTheDocument()
    // A short page is the last one; an order already shown is not repeated.
    expect(screen.queryByRole('button', { name: 'Load more orders' })).not.toBeInTheDocument()
    expect(screen.getAllByText('Buyer 3')).toHaveLength(1)
  })

  it('offers no "load more" when everything fits on one page', async () => {
    await renderOrders([order({})])
    expect(screen.queryByRole('button', { name: 'Load more orders' })).not.toBeInTheDocument()
  })

  it('filters by status on the server', async () => {
    await renderOrders([order({})])
    fireEvent.change(screen.getByRole('combobox', { name: 'Show orders' }), { target: { value: 'paid' } })
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/sites/s-1/orders?limit=50&offset=0&status=paid'))
  })

  it('searches on the server once typing pauses', async () => {
    await renderOrders([order({})])
    fireEvent.change(screen.getByRole('textbox', { name: 'Search orders' }), { target: { value: ' ana ' } })
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/sites/s-1/orders?limit=50&offset=0&q=ana'))
  })

  it('says when nothing matches a filter, not that the store has no orders', async () => {
    await renderOrders([order({})])
    api.get.mockResolvedValue([])
    fireEvent.change(screen.getByRole('combobox', { name: 'Show orders' }), { target: { value: 'refunded' } })
    expect(await screen.findByText('No orders match.')).toBeInTheDocument()
  })

  it('tells orders apart by customer and what was bought', async () => {
    await renderOrders([order({ items_summary: 'Mug × 2, Tea, Spoon', item_count: 5, receipt_number: 'LUM-00042' })])
    expect(screen.getByText('Buyer')).toBeInTheDocument()
    expect(screen.getByText(/Mug × 2, Tea, Spoon/)).toBeInTheDocument()
    expect(screen.getByText(/5 items/)).toBeInTheDocument()
    expect(screen.getByText(/LUM-00042/)).toBeInTheDocument()
  })
})

describe('Orders — the detail view', () => {
  async function openOrder(over: Partial<CappeOrder>) {
    const full = order({ items: [line()], ...over })
    await renderOrders([order(over)])
    api.get.mockResolvedValue(full)
    fireEvent.click(screen.getByRole('button', { name: 'Show order details' }))
    await screen.findByText('2 × Mug')
  }

  it('shows how the total was made up, the note, and any refund', async () => {
    await openOrder({
      subtotal_cents: 4000, tax_cents: 350, shipping_cents: 600, total_cents: 4950,
      refunded_cents: 1000, note: 'Gift wrap, please',
    })
    expect(screen.getByText('Gift wrap, please')).toBeInTheDocument()
    expect(screen.getByText('Tax', { selector: 'dt' }).nextSibling?.textContent).toBe('$3.50')
    expect(screen.getByText('Shipping', { selector: 'dt' }).nextSibling?.textContent).toBe('$6.00')
    expect(screen.getByText('Total', { selector: 'dt' }).nextSibling?.textContent).toBe('$49.50')
    expect(screen.getByText('Refunded', { selector: 'dt' }).nextSibling?.textContent).toBe('−$10.00')
  })

  it('offers tracking on a paid order and can fulfil it in the same step', async () => {
    api.patch.mockResolvedValue(order({ status: 'fulfilled', carrier: 'USPS', tracking_number: '9400' }))
    await openOrder({ status: 'paid' })
    fireEvent.change(screen.getByRole('textbox', { name: 'Carrier' }), { target: { value: 'USPS' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Tracking number' }), { target: { value: '9400' } })
    fireEvent.click(screen.getByRole('button', { name: /Save & mark fulfilled/ }))
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/sites/s-1/orders/o-1', {
      carrier: 'USPS', tracking_number: '9400', status: 'fulfilled',
    }))
    expect(await screen.findByText('fulfilled')).toBeInTheDocument()
  })

  it('does not offer tracking on an order that will never ship', async () => {
    await openOrder({ status: 'pending', payment_ref: null })
    expect(screen.queryByRole('textbox', { name: 'Tracking number' })).not.toBeInTheDocument()
  })

  it('still shows tracking already recorded on a refunded order', async () => {
    await openOrder({ status: 'refunded', carrier: 'UPS', tracking_number: '1Z9' })
    expect(screen.queryByRole('textbox', { name: 'Tracking number' })).not.toBeInTheDocument()
    expect(screen.getByText('Tracking: UPS 1Z9')).toBeInTheDocument()
  })
})
