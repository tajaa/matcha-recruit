import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PromoCodesCard from './PromoCodesCard'
import { EMPTY, toBody } from '../utils/promoCodes'
import type { CappePromoCode, CappePromoCodes } from '../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api }))

const CODE: CappePromoCode = {
  id: 'c-1', code: 'SAVE10', kind: 'percent', percent_off: 10, amount_off_cents: null, min_subtotal_cents: 5000,
  starts_on: null, ends_on: null, max_redemptions: 100, once_per_customer: true, active: true,
  redemption_count: 7, created_at: '2026-10-01T00:00:00Z',
}

function load(data: CappePromoCodes) {
  api.get.mockResolvedValue(data)
  render(<MemoryRouter><PromoCodesCard siteId="s-1" /></MemoryRouter>)
}

beforeEach(() => {
  api.get.mockReset(); api.post.mockReset(); api.put.mockReset(); api.delete.mockReset()
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

describe('PromoCodesCard', () => {
  it('lists codes with what they take off and how often they were used', async () => {
    load({ enabled: true, currency: 'USD', codes: [CODE] })
    expect(await screen.findByText('SAVE10')).toBeInTheDocument()
    expect(screen.getByText('10% off · over $50.00 · once per customer')).toBeInTheDocument()
    expect(screen.getByText('Used 7 of 100')).toBeInTheDocument()
  })

  it('follows a currency change made after it loaded', async () => {
    api.get.mockResolvedValue({ enabled: true, currency: 'USD', codes: [CODE] })
    const { rerender } = render(<MemoryRouter><PromoCodesCard siteId="s-1" /></MemoryRouter>)
    expect(await screen.findByText('10% off · over $50.00 · once per customer')).toBeInTheDocument()
    rerender(<MemoryRouter><PromoCodesCard siteId="s-1" currency="GBP" /></MemoryRouter>)
    expect(screen.getByText('10% off · over £50.00 · once per customer')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledTimes(1)
  })

  it('creates a code', async () => {
    load({ enabled: true, currency: 'USD', codes: [] })
    fireEvent.click(await screen.findByRole('button', { name: /New code/ }))
    fireEvent.change(screen.getByLabelText('Code'), { target: { value: 'fall5' } })
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'fixed' } })
    fireEvent.change(screen.getByLabelText('Amount (USD)'), { target: { value: '5' } })
    api.post.mockResolvedValue({ ...CODE, id: 'c-2', code: 'FALL5', kind: 'fixed', percent_off: null, amount_off_cents: 500 })
    fireEvent.click(screen.getByRole('button', { name: 'Create code' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/promo-codes', expect.objectContaining({
      code: 'FALL5', kind: 'fixed', amount_off_cents: 500, percent_off: null,
    })))
    expect(await screen.findByText('FALL5')).toBeInTheDocument()
  })

  it('shows why the server refused a code', async () => {
    load({ enabled: true, currency: 'USD', codes: [] })
    fireEvent.click(await screen.findByRole('button', { name: /New code/ }))
    fireEvent.change(screen.getByLabelText('Code'), { target: { value: 'SAVE10' } })
    fireEvent.change(screen.getByLabelText('Percent'), { target: { value: '10' } })
    api.post.mockRejectedValue(new Error('You already have a code called SAVE10.'))
    fireEvent.click(screen.getByRole('button', { name: 'Create code' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('already have a code called SAVE10')
  })

  it('edits and deletes a code', async () => {
    load({ enabled: true, currency: 'USD', codes: [CODE] })
    fireEvent.click(await screen.findByRole('button', { name: 'Edit SAVE10' }))
    fireEvent.change(screen.getByLabelText('Percent'), { target: { value: '15' } })
    api.put.mockResolvedValue({ ...CODE, percent_off: 15 })
    fireEvent.click(screen.getByRole('button', { name: 'Save code' }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/sites/s-1/promo-codes/c-1', expect.objectContaining({ percent_off: 15 })))
    expect(await screen.findByText(/15% off/)).toBeInTheDocument()
    api.delete.mockResolvedValue(undefined)
    fireEvent.click(screen.getByRole('button', { name: 'Delete SAVE10' }))
    await waitFor(() => expect(screen.queryByText('SAVE10')).not.toBeInTheDocument())
  })

  it('offers the plan instead of a form when codes are not included', async () => {
    load({ enabled: false, currency: 'USD', codes: [] })
    expect(await screen.findByRole('link', { name: 'See plans' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /New code/ })).not.toBeInTheDocument()
  })
})

describe('promo code form', () => {
  it('refuses what the server would', () => {
    expect(toBody({ ...EMPTY, code: 'a b', value: '10' })).toMatch(/letters, numbers/)
    expect(toBody({ ...EMPTY, code: 'OK1', value: '95' })).toMatch(/1 to 90/)
    expect(toBody({ ...EMPTY, code: 'OK1', kind: 'fixed', value: '1,299' })).toMatch(/amount off/)
    expect(toBody({ ...EMPTY, code: 'OK1', value: '10', cap: '0' })).toMatch(/Total uses/)
    expect(toBody({ ...EMPTY, code: 'OK1', value: '10', starts: '2026-10-09', ends: '2026-10-01' })).toMatch(/end date/)
  })

  it('builds the body for a percent code', () => {
    expect(toBody({ ...EMPTY, code: 'save10', value: '10', minimum: '50', cap: '100', once: true })).toEqual({
      code: 'SAVE10', kind: 'percent', percent_off: 10, amount_off_cents: null, min_subtotal_cents: 5000,
      starts_on: null, ends_on: null, max_redemptions: 100, once_per_customer: true, active: true,
    })
  })
})
