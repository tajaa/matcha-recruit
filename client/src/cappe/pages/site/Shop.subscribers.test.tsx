import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Shop from './Shop'
import { CappeApiError } from '../../api'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('../../api', async (importOriginal) => ({ ...(await importOriginal<object>()), cappeApi: api }))
vi.mock('../../components/TaxSettingsCard', () => ({ default: () => null }))
vi.mock('../../components/ShippingSettingsCard', () => ({ default: () => null }))
vi.mock('../../components/ImageUpload', () => ({ default: () => null }))

const product = {
  id: 'p-1', site_id: 's-1', name: 'Beans', description: null, price_cents: 1500, currency: 'USD', image_url: null,
  sku: null, inventory: null, low_stock_threshold: null, status: 'active', sort_order: 0, fulfillment: 'physical',
  digital_file_url: null, booking_type_id: null, requires_approval: false, intake_fields: [], category: null,
  option_groups: [], created_at: '', updated_at: '', subscription_intervals: ['month'], subscription_discount_bps: 0,
}
const refusal = () => new CappeApiError('2 customer subscriptions include this product. Ending them stops their renewals after the period already paid for.', 'has_subscriptions', 409)

function renderShop() {
  render(
    <MemoryRouter initialEntries={['/sites/s-1/shop']}>
      <Routes><Route path="/sites/:siteId/shop" element={<Shop />} /></Routes>
    </MemoryRouter>,
  )
}

let confirm: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset()
  api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/products') ? [product] : []))
  confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
})

describe('Shop — a product customers subscribe to', () => {
  it('asks before archiving it, then ends the subscriptions with the archive', async () => {
    api.put.mockRejectedValueOnce(refusal()).mockResolvedValueOnce({ ...product, status: 'archived' })
    renderShop()
    fireEvent.change(await screen.findByRole('combobox', { name: 'Status of Beans' }), { target: { value: 'archived' } })
    await waitFor(() => expect(api.put).toHaveBeenLastCalledWith('/sites/s-1/products/p-1?end_subscriptions=true', { status: 'archived' }))
    expect(confirm.mock.calls[0][0]).toContain('2 customer subscriptions include this product')
  })

  it('leaves everything alone when the owner says no', async () => {
    confirm.mockReturnValue(false)
    api.put.mockRejectedValueOnce(refusal())
    renderShop()
    fireEvent.change(await screen.findByRole('combobox', { name: 'Status of Beans' }), { target: { value: 'archived' } })
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('asks the same before deleting it', async () => {
    api.delete.mockRejectedValueOnce(refusal()).mockResolvedValueOnce(undefined)
    renderShop()
    fireEvent.click(await screen.findByRole('button', { name: 'Delete Beans' }))
    await waitFor(() => expect(api.delete).toHaveBeenLastCalledWith('/sites/s-1/products/p-1?end_subscriptions=true'))
    await waitFor(() => expect(screen.queryByText('Beans')).not.toBeInTheDocument())
  })
})
