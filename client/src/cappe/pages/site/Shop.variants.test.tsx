import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Shop from './Shop'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('../../api', async (importOriginal) => ({ ...(await importOriginal<object>()), cappeApi: api }))
vi.mock('../../components/TaxSettingsCard', () => ({ default: () => null }))
vi.mock('../../components/ShippingSettingsCard', () => ({ default: () => null }))
vi.mock('../../components/PromoCodesCard', () => ({ default: () => null }))
vi.mock('../../components/ImageUpload', () => ({ default: () => null }))

const tee = {
  id: 'p-1', site_id: 's-1', name: 'Tee', description: null, price_cents: 2000, currency: 'USD', image_url: null,
  sku: 'TEE', inventory: null, low_stock_threshold: null, status: 'active', sort_order: 0, fulfillment: 'physical',
  digital_file_url: null, booking_type_id: null, requires_approval: false, intake_fields: [], category: null,
  option_groups: [
    { id: 'g-size', name: 'Size', select_type: 'single', required: true, sort_order: 0,
      options: [{ id: 's', name: 'S', price_delta_cents: 0, sort_order: 0, inventory: null }, { id: 'm', name: 'M', price_delta_cents: 0, sort_order: 1, inventory: null }] },
  ],
  variants: [{ id: 'v-m', option_ids: ['m'], sku: 'TEE-M', price_cents: null, inventory: 2, image_url: null, status: 'active', sort_order: 0 }],
  created_at: '', updated_at: '', subscription_intervals: [], subscription_discount_bps: 0,
}

function plan(code: string, name: string, allowed: string[]) {
  return { plan_code: code, plan_name: name, can_sell: true, platform_fee_bps: 200, allowed_fulfillment: allowed, features: {} }
}

function renderShop(entitlements = plan('business', 'Business', ['booking', 'digital', 'physical', 'service'])) {
  api.get.mockImplementation((path: string) => Promise.resolve(
    path.endsWith('/products') ? [tee] : path === '/billing/entitlements' ? entitlements : [],
  ))
  render(
    <MemoryRouter initialEntries={['/sites/s-1/shop']}>
      <Routes><Route path="/sites/:siteId/shop" element={<Shop />} /></Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset()
})

describe('Shop — variants', () => {
  it('shows each combination and saves its stock with the count the form showed', async () => {
    api.put.mockResolvedValue(tee)
    renderShop()
    fireEvent.click(await screen.findByRole('button', { name: 'Edit Tee' }))
    expect(screen.getByRole('checkbox', { name: /Track each combination separately/ })).toBeChecked()
    // The size options' own stock boxes are gone: a variant owns that stock.
    expect(screen.queryByTitle("This option's own stock (blank = untracked)")).not.toBeInTheDocument()
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Stock for M' }), { target: { value: '5' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'SKU for S' }), { target: { value: 'TEE-S' } })
    fireEvent.click(screen.getByRole('button', { name: /Save changes/ }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const body = api.put.mock.calls[0][1]
    expect(body.variants).toEqual([
      { options: [{ group: 'Size', option: 'S' }], sku: 'TEE-S', price_cents: null, image_url: null, status: 'active' },
      { id: 'v-m', options: [{ group: 'Size', option: 'M' }], sku: 'TEE-M', price_cents: null, image_url: null,
        status: 'active', inventory: 5, expected_inventory: 2 },
    ])
  })

  it('turning variants off removes the ones the product had', async () => {
    api.put.mockResolvedValue({ ...tee, variants: [] })
    renderShop()
    fireEvent.click(await screen.findByRole('button', { name: 'Edit Tee' }))
    fireEvent.click(screen.getByRole('checkbox', { name: /Track each combination separately/ }))
    fireEvent.click(screen.getByRole('button', { name: /Save changes/ }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    expect(api.put.mock.calls[0][1].variants).toEqual([])
  })
})

describe('Shop — what the plan sells', () => {
  it('says which products shoppers cannot buy and does not offer that kind', async () => {
    renderShop(plan('free', 'Free', ['booking', 'digital', 'service']))
    expect(await screen.findByText(/Your Free plan doesn't sell physical products/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'See plans' })).toBeInTheDocument()
    expect(screen.getByText('not on your plan')).toBeInTheDocument()
    const physical = screen.getByRole('button', { name: /Physical good/ })
    await waitFor(() => expect(physical).toBeDisabled())
    expect(within(physical).getByText('Not on the Free plan')).toBeInTheDocument()
    // A new product starts as something the plan sells.
    expect(screen.getByRole('button', { name: /Digital download/ }).className).toContain('border-emerald-500')
  })
})
