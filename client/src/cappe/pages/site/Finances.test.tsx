import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Finances from './Finances'
import { groupFor, presetWindow } from '../../utils/finances'
import type { CappeBalance, CappeFinancials } from '../../types'

const api = vi.hoisted(() => ({ get: vi.fn(), openBlob: vi.fn() }))
vi.mock('../../api', () => ({ cappeApi: api }))

function fin(over: Partial<CappeFinancials> = {}): CappeFinancials {
  return {
    currency: 'USD', start: '2026-09-07', end: '2026-10-06', group: 'day',
    orders: 4, gross_cents: 20000, goods_cents: 17000, tax_cents: 1500, shipping_cents: 1500,
    platform_fee_cents: 400, refunds_cents: 3000, refund_count: 2, net_cents: 16600, average_order_cents: 5000,
    series: [
      { period: '2026-10-05', orders: 4, gross_cents: 20000, refunds_cents: 0 },
      { period: '2026-10-06', orders: 0, gross_cents: 0, refunds_cents: 3000 },
    ],
    top_products: [{ product_id: 'p-1', title: 'Mug', units: 5, revenue_cents: 10000 }],
    other_currency_orders: 0, export_enabled: true, ...over,
  }
}

const BALANCE: CappeBalance = {
  connected: true, available: [{ amount_cents: 12345, currency: 'USD' }], pending: [],
  payouts: [{ id: 'po_1', amount_cents: 9000, currency: 'USD', status: 'in_transit', arrival_date: 1760000000 }],
}

function load(f: CappeFinancials | Error, balance: CappeBalance | Error = BALANCE) {
  api.get.mockImplementation((path: string) => {
    const value = path === '/payments/balance' ? balance : f
    return value instanceof Error ? Promise.reject(value) : Promise.resolve(value)
  })
  render(
    <MemoryRouter initialEntries={['/sites/s-1/finances']}>
      <Routes><Route path="/sites/:siteId/finances" element={<Finances />} /></Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.get.mockReset()
  api.openBlob.mockReset()
})

describe('Finances', () => {
  it('shows sales, refunds, fees and what is left', async () => {
    load(fin())
    expect(await screen.findByText('$166.00')).toBeInTheDocument()
    expect(screen.getAllByText('$200.00').length).toBeGreaterThan(0)   // the stat, and the chart's table
    expect(screen.getByText('−$30.00')).toBeInTheDocument()
    expect(screen.getByText('−$4.00')).toBeInTheDocument()
    expect(screen.getByText('Average order $50.00')).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'Mug' })).toBeInTheDocument()
    expect(screen.getByText('$123.45')).toBeInTheDocument()            // Stripe balance
    expect(api.get.mock.calls[0][0]).toMatch(/^\/sites\/s-1\/financials\?start=\d{4}-\d\d-\d\d&end=\d{4}-\d\d-\d\d&group=day$/)
  })

  it('asks again with weekly buckets for a longer period', async () => {
    load(fin())
    await screen.findByText('$166.00')
    fireEvent.change(screen.getByLabelText('Period'), { target: { value: '90' } })
    await waitFor(() => expect(api.get.mock.calls.some(([p]) => String(p).endsWith('&group=week'))).toBe(true))
  })

  it('exports orders as CSV when the plan allows', async () => {
    load(fin())
    fireEvent.click(await screen.findByRole('button', { name: /Export orders/ }))
    await waitFor(() => expect(api.openBlob).toHaveBeenCalled())
    expect(api.openBlob.mock.calls[0][0]).toMatch(/\/financials\/export\.csv\?kind=orders&start=/)
  })

  it('offers no export on a plan without it', async () => {
    load(fin({ export_enabled: false }))
    await screen.findByText('$166.00')
    expect(screen.queryByRole('button', { name: /Export/ })).not.toBeInTheDocument()
    expect(screen.getByText(/comes with paid plans/)).toBeInTheDocument()
  })

  it('says orders in an old currency are left out', async () => {
    load(fin({ other_currency_orders: 3 }))
    expect(await screen.findByText(/3 orders in another currency/)).toBeInTheDocument()
  })

  it('shows an error with a retry instead of zeros', async () => {
    load(new Error('Server error'))
    expect(await screen.findByRole('alert')).toHaveTextContent('Couldn’t load your finances')
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
    api.get.mockImplementation((path: string) => Promise.resolve(path === '/payments/balance' ? BALANCE : fin()))
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('$166.00')).toBeInTheDocument()
  })

  it('says when Stripe is not connected', async () => {
    load(fin(), { connected: false, available: [], pending: [], payouts: [] })
    expect(await screen.findByText(/Connect Stripe/)).toBeInTheDocument()
  })
})

describe('finance windows', () => {
  it('ends a preset today', () => {
    expect(presetWindow('7', new Date(2026, 9, 6))).toEqual(['2026-09-30', '2026-10-06'])
    expect(presetWindow('30', new Date(2026, 9, 6))).toEqual(['2026-09-07', '2026-10-06'])
  })

  it('buckets by day, week or month by length', () => {
    expect(groupFor('2026-09-07', '2026-10-06')).toBe('day')
    expect(groupFor('2026-07-09', '2026-10-06')).toBe('week')
    expect(groupFor('2025-10-07', '2026-10-06')).toBe('month')
  })
})
