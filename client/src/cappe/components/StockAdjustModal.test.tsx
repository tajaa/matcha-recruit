import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StockAdjustModal from './StockAdjustModal'
import type { CappeProduct } from '../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api', async (importOriginal) => ({ ...(await importOriginal<object>()), cappeApi: api }))

const tee = {
  id: 'p-1', name: 'Tee', inventory: null,
  option_groups: [{ id: 'g', name: 'Size', select_type: 'single', required: true, sort_order: 0,
    options: [{ id: 'm', name: 'M', price_delta_cents: 0, sort_order: 0, inventory: null }] }],
  variants: [{ id: 'v-m', option_ids: ['m'], sku: null, price_cents: null, inventory: 2, image_url: null, status: 'active', sort_order: 0 }],
} as unknown as CappeProduct

beforeEach(() => {
  api.get.mockReset().mockResolvedValue([
    { id: 'a1', product_id: 'p-1', option_id: null, variant_id: 'v-m', delta: -1, balance_after: 2, reason: 'sale', note: null, created_at: '2026-10-20T00:00:00Z' },
  ])
  api.post.mockReset().mockResolvedValue(tee)
})

describe('StockAdjustModal — combinations', () => {
  it('starts on the combination when the product keeps no count of its own, and adjusts it', async () => {
    render(<StockAdjustModal siteId="s-1" product={tee} onClose={() => {}} onUpdated={() => {}} />)
    expect(await screen.findByText(/sale · M/)).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Stock to adjust' })).toHaveValue('v:v-m')
    fireEvent.click(screen.getByRole('button', { name: /Apply/ }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/products/p-1/adjust', {
      delta: 1, option_id: null, variant_id: 'v-m', reason: 'restock', note: null,
    }))
  })
})
