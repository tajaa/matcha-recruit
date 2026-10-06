import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Subscriptions from './Subscriptions'
import type { CappeShopperSubscription } from '../../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../../api', () => ({ cappeApi: api }))

function sub(over: Partial<CappeShopperSubscription> = {}): CappeShopperSubscription {
  return {
    id: 'sub-1', status: 'active', interval: 'month', items: [{ title: 'Beans', quantity: 2 }],
    total_cents: 2660, currency: 'USD', cancel_at_period_end: false, current_period_end: '2026-11-06T12:00:00Z',
    customer_name: 'Ana', customer_email: 'ana@example.com', order_count: 3, last_order_at: '2026-10-06T12:00:00Z',
    ...over,
  }
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/sites/s-1/subscriptions']}>
      <Routes><Route path="/sites/:siteId/subscriptions" element={<Subscriptions />} /></Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

describe('Subscriptions', () => {
  it('names the customer and says when it renews and what it has produced', async () => {
    api.get.mockResolvedValueOnce([sub()])
    renderPage()
    expect(await screen.findByText('Ana')).toBeInTheDocument()
    expect(screen.getByText(/\$26\.60 every month · renews Nov 6, 2026 · 3 orders, last Oct 6, 2026/)).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/sites/s-1/subscriptions?limit=50&offset=0')
  })

  it('ends after the period, or now, and can be kept going', async () => {
    api.get.mockResolvedValueOnce([sub()])
    api.post.mockResolvedValueOnce({ status: 'active', cancel_at_period_end: true })
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'End after this period' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/subscriptions/sub-1/cancel'))
    expect(await screen.findByText('Ending')).toBeInTheDocument()

    api.post.mockResolvedValueOnce({ status: 'active', cancel_at_period_end: false })
    fireEvent.click(screen.getByRole('button', { name: 'Keep it going' }))
    await waitFor(() => expect(api.post).toHaveBeenLastCalledWith('/sites/s-1/subscriptions/sub-1/resume'))

    api.post.mockResolvedValueOnce({ status: 'canceled', cancel_at_period_end: false })
    fireEvent.click(await screen.findByRole('button', { name: 'End now' }))
    await waitFor(() => expect(api.post).toHaveBeenLastCalledWith('/sites/s-1/subscriptions/sub-1/cancel?immediate=true'))
    expect(await screen.findByText('Ended')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'End now' })).not.toBeInTheDocument()
  })

  it('shows a failed load as an error with a retry, not as "no subscriptions"', async () => {
    api.get.mockRejectedValueOnce(new Error('Server error — try again in a moment.'))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Couldn’t load subscriptions')
    expect(screen.queryByText(/No subscriptions yet/)).not.toBeInTheDocument()
    api.get.mockResolvedValueOnce([sub()])
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Ana')).toBeInTheDocument()
  })

  it('hides abandoned checkouts unless asked', async () => {
    api.get.mockResolvedValue([])
    renderPage()
    expect(await screen.findByText(/No subscriptions yet/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /never finished/ }))
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/sites/s-1/subscriptions?limit=50&offset=0&include_abandoned=true'))
  })
})
