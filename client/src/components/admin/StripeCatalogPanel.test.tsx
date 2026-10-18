import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { StripeCatalogPanel } from './StripeCatalogPanel'
import { connectStripeCatalogWebhook, fetchStripeCatalog, saveStripeCatalogDetails, syncStripeCatalog } from '../../api/admin/stripeCatalog'
import type { StripeCatalog } from '../../types/stripeCatalog'

vi.mock('../../api/admin/stripeCatalog', () => ({
  fetchStripeCatalog: vi.fn(), syncStripeCatalog: vi.fn(), connectStripeCatalogWebhook: vi.fn(), saveStripeCatalogDetails: vi.fn(),
}))

const catalog: StripeCatalog = {
  configured: true, account_id: 'acct_matcha', livemode: false, webhook: {},
  products: ['incidents', 'scheduler'].map((key) => ({
    key: key as 'incidents' | 'scheduler', name: key === 'incidents' ? 'Matcha Incidents' : 'Matcha Scheduler',
    display_name: key === 'incidents' ? 'Matcha Incidents' : 'Matcha Scheduler', description: '',
    active: true, status: 'not_synced', prices: [], error: null,
    stripe_product_id: null, synced_at: null, webhook_verified_at: null,
  })),
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(fetchStripeCatalog).mockResolvedValue(catalog)
})

describe('Stripe catalog controls', () => {
  it('shows only the two commercial products and the selected Stripe mode', async () => {
    render(<StripeCatalogPanel />)
    expect(await screen.findByText('Matcha Incidents')).toBeInTheDocument()
    expect(screen.getByText('Matcha Scheduler')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Sync' })).toHaveLength(2)
    expect(screen.getByText('Test mode')).toBeInTheDocument()
    expect(screen.queryByText('Espresso')).not.toBeInTheDocument()
  })

  it('syncs only the selected product and shows webhook confirmation separately', async () => {
    vi.mocked(syncStripeCatalog).mockResolvedValue({ ...catalog, products: [
      { ...catalog.products[0], status: 'synced', stripe_product_id: 'prod_incidents', synced_at: '2026-10-17T18:00:00Z' },
      catalog.products[1],
    ] })
    render(<StripeCatalogPanel />)
    fireEvent.click((await screen.findAllByRole('button', { name: 'Sync' }))[0])
    await waitFor(() => expect(syncStripeCatalog).toHaveBeenCalledWith('incidents'))
    expect(await screen.findByText('Saved in Stripe; awaiting webhook confirmation.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View in Stripe' })).toHaveAttribute('href', 'https://dashboard.stripe.com/test/products/prod_incidents')
  })

  it('keeps a failed sync actionable without claiming the saved admin price was lost', async () => {
    vi.mocked(syncStripeCatalog).mockRejectedValue(new Error('Stripe timed out. Retry syncing this product.'))
    render(<StripeCatalogPanel />)
    fireEvent.click((await screen.findAllByRole('button', { name: 'Sync' }))[0])
    expect(await screen.findByRole('alert')).toHaveTextContent('Stripe timed out')
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Sync' })[0]).not.toBeDisabled())
  })

  it('connects catalog events through the existing webhook controls', async () => {
    vi.mocked(connectStripeCatalogWebhook).mockResolvedValue({ url: 'https://example.com/api/webhooks/stripe', catalog_events_enabled: true })
    vi.mocked(fetchStripeCatalog).mockResolvedValueOnce(catalog).mockResolvedValue({ ...catalog, webhook: { catalog_events_enabled: true } })
    render(<StripeCatalogPanel />)
    fireEvent.click(await screen.findByRole('button', { name: 'Connect catalog webhooks' }))
    expect(await screen.findByText('Catalog events connected to your existing Stripe webhook.')).toBeInTheDocument()
    expect(connectStripeCatalogWebhook).toHaveBeenCalledOnce()
  })

  it('disables Stripe mutations when server credentials are missing', async () => {
    vi.mocked(fetchStripeCatalog).mockResolvedValue({ ...catalog, configured: false, account_id: null, livemode: null })
    render(<StripeCatalogPanel />)
    const buttons = await screen.findAllByRole('button', { name: 'Sync' })
    expect(buttons.every((button) => button.hasAttribute('disabled'))).toBe(true)
    expect(screen.getByRole('button', { name: 'Connect catalog webhooks' })).toBeDisabled()
  })

  it('edits customer-facing product details without accepting Stripe IDs or prices from the form', async () => {
    vi.mocked(saveStripeCatalogDetails).mockResolvedValue({ ...catalog, products: [
      { ...catalog.products[0], display_name: 'Matcha Incident Reporting' }, catalog.products[1],
    ] })
    render(<StripeCatalogPanel />)
    const inputs = await screen.findAllByLabelText('Checkout name')
    fireEvent.change(inputs[0], { target: { value: 'Matcha Incident Reporting' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Save product details' })[0])
    await waitFor(() => expect(saveStripeCatalogDetails).toHaveBeenCalledWith('incidents', { name: 'Matcha Incident Reporting', description: '' }))
  })

  it('refreshes a pending signed webhook confirmation without requiring another sync', async () => {
    vi.useFakeTimers()
    try {
      const pending: StripeCatalog = { ...catalog, webhook: { catalog_events_enabled: true }, products: [
        { ...catalog.products[0], status: 'synced', synced_at: '2026-10-17T18:00:00Z' }, catalog.products[1],
      ] }
      vi.mocked(fetchStripeCatalog).mockResolvedValueOnce(pending).mockResolvedValue({ ...pending, products: [
        { ...pending.products[0], webhook_verified_at: '2026-10-17T18:00:03Z' }, pending.products[1],
      ] })
      await act(async () => { render(<StripeCatalogPanel />) })
      expect(screen.getByText('Saved in Stripe; awaiting webhook confirmation.')).toBeInTheDocument()
      await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
      expect(screen.getByText(/Webhook confirmed/)).toBeInTheDocument()
      expect(syncStripeCatalog).not.toHaveBeenCalled()
    } finally { vi.useRealTimers() }
  })
})
