import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Shop from './Shop'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('../../api', async (importOriginal) => ({ ...(await importOriginal<object>()), cappeApi: api }))
vi.mock('../../components/TaxSettingsCard', () => ({ default: () => null }))
vi.mock('../../components/PromoCodesCard', () => ({ default: () => null }))
vi.mock('../../components/ImageUpload', () => ({ default: () => null }))
// The shipping card reports the store's country when it loads — here, on a click.
vi.mock('../../components/ShippingSettingsCard', () => ({
  default: ({ onHomeCountryChange }: { onHomeCountryChange: (c: string) => void }) => (
    <button type="button" onClick={() => onHomeCountryChange('US')}>Store is in the US</button>
  ),
}))

const box = {
  id: 'p-1', site_id: 's-1', name: 'Box', description: null, price_cents: 2000, currency: 'USD', image_url: null,
  sku: null, inventory: null, low_stock_threshold: null, status: 'active', sort_order: 0, fulfillment: 'physical',
  digital_file_url: null, booking_type_id: null, requires_approval: false, intake_fields: [], category: null,
  option_groups: [], variants: [], weight_g: 1000, shipping_surcharge_cents: 0, ships_free: false,
  created_at: '', updated_at: '', subscription_intervals: [], subscription_discount_bps: 0,
}

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset()
  api.get.mockImplementation((path: string) => Promise.resolve(
    path.endsWith('/products') ? [box]
      : path === '/billing/entitlements'
        ? { plan_code: 'business', plan_name: 'Business', can_sell: true, platform_fee_bps: 200,
            allowed_fulfillment: ['booking', 'digital', 'physical', 'service'], features: {} }
        : [],
  ))
  api.put.mockResolvedValue(box)
})

function renderShop() {
  render(
    <MemoryRouter initialEntries={['/sites/s-1/shop']}>
      <Routes><Route path="/sites/:siteId/shop" element={<Shop />} /></Routes>
    </MemoryRouter>,
  )
}

describe('Shop — weight unit', () => {
  it('keeps reading a shown weight in the unit it was shown in when the store country arrives', async () => {
    renderShop()
    fireEvent.click(await screen.findByRole('button', { name: 'Edit Box' }))
    expect(screen.getByRole('textbox', { name: 'Weight per item (kg)' })).toHaveValue('1')
    fireEvent.click(screen.getByRole('button', { name: 'Store is in the US' }))
    fireEvent.click(screen.getByRole('button', { name: /Save changes/ }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    // 1 kg stays 1000 g — not re-read as 1 lb (454 g).
    expect(api.put.mock.calls[0][1].weight_g).toBe(1000)
  })

  it('follows the store country again for the next product', async () => {
    renderShop()
    fireEvent.click(await screen.findByRole('button', { name: 'Store is in the US' }))
    expect(screen.getByRole('textbox', { name: 'Weight per item (lb)' })).toHaveValue('')
    fireEvent.change(screen.getByRole('textbox', { name: 'Weight per item (lb)' }), { target: { value: '2' } })
    expect(screen.getByRole('textbox', { name: 'Weight per item (lb)' })).toHaveValue('2')
  })
})
