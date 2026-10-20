import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ShippingSettingsCard from './ShippingSettingsCard'
import StockAdjustModal from './StockAdjustModal'
import StripeConnectCard from './StripeConnectCard'
import TaxSettingsCard from './TaxSettingsCard'
import type { CappeProduct } from '../types'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api }))

beforeEach(() => {
  api.get.mockReset()
  api.put.mockReset()
  api.post.mockReset()
})

describe.each([
  ['TaxSettingsCard', TaxSettingsCard, 'tax settings'],
  ['ShippingSettingsCard', ShippingSettingsCard, 'shipping settings'],
])('%s — a failed load', (_name, Card, noun) => {
  it('offers no form to save, so blank boxes cannot overwrite the real settings', async () => {
    api.get.mockRejectedValueOnce(new Error('Server error — try again in a moment.'))
    render(<MemoryRouter><Card siteId="s-1" /></MemoryRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent(`Couldn’t load your ${noun}`)
    expect(screen.queryByRole('button', { name: /Save/ })).not.toBeInTheDocument()
    expect(api.put).not.toHaveBeenCalled()
  })

  it('loads the form on retry', async () => {
    api.get.mockRejectedValueOnce(new Error('down'))
    render(<MemoryRouter><Card siteId="s-1" /></MemoryRouter>)
    api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/shipping-zones')
      ? { enabled: false, home_country: 'US', currency: 'USD', countries: ['US', 'CA'], zones: [] }
      : { tax_rate_bps: 875, shipping_flat_cents: 600 }))
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('button', { name: /Save/ })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('TaxSettingsCard — how tax is charged', () => {
  it('loads and saves whether prices include tax and whether shipping is taxed', async () => {
    api.get.mockResolvedValue({ tax_rate_bps: 2000, tax_label: 'VAT', prices_include_tax: true, tax_on_shipping: false })
    api.put.mockResolvedValue({})
    render(<TaxSettingsCard siteId="s-1" />)
    const included = await screen.findByRole('checkbox', { name: /My prices already include VAT/ })
    expect(included).toBeChecked()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Charge VAT on shipping too' }))
    fireEvent.click(screen.getByRole('button', { name: /Save/ }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/sites/s-1', expect.objectContaining({
      tax_rate_bps: 2000, tax_label: 'VAT', prices_include_tax: true, tax_on_shipping: true,
    })))
  })
})

describe('TaxSettingsCard — switching what prices mean', () => {
  it('asks before prices start including tax, and sends nothing if the owner backs out', async () => {
    api.get.mockResolvedValue({ tax_rate_bps: 2000, tax_label: 'VAT', prices_include_tax: false })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    render(<TaxSettingsCard siteId="s-1" />)
    fireEvent.click(await screen.findByRole('checkbox', { name: /My prices already include VAT/ }))
    fireEvent.click(screen.getByRole('button', { name: /Save/ }))
    expect(confirm).toHaveBeenLastCalledWith(expect.stringContaining('with the VAT inside it'))
    expect(api.put).not.toHaveBeenCalled()
    api.put.mockResolvedValue({})
    fireEvent.click(screen.getByRole('button', { name: /Save/ }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/sites/s-1', expect.objectContaining({ prices_include_tax: true })))
    // Saved: the next save of the same setting doesn't ask again.
    await screen.findByText('Saved')
    fireEvent.click(screen.getByRole('button', { name: /Save/ }))
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
    expect(confirm).toHaveBeenCalledTimes(2)
    confirm.mockRestore()
  })

  it('warns that turning it off makes checkout cost more', async () => {
    api.get.mockResolvedValue({ tax_rate_bps: 2000, tax_label: 'VAT', prices_include_tax: true })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<TaxSettingsCard siteId="s-1" />)
    fireEvent.click(await screen.findByRole('checkbox', { name: /My prices already include VAT/ }))
    fireEvent.click(screen.getByRole('button', { name: /Save/ }))
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('will cost buyers more at checkout'))
    confirm.mockRestore()
  })
})

describe('StockAdjustModal — the stock history', () => {
  const product = {
    id: 'p-1', name: 'Mug', inventory: 4, option_groups: [
      { id: 'g-1', name: 'Colour', options: [{ id: 'opt-1', name: 'Blue', inventory: 2 }] },
    ],
  } as unknown as CappeProduct

  it('says the history could not be loaded instead of claiming there is none', async () => {
    api.get.mockRejectedValueOnce(new Error('boom'))
    render(<StockAdjustModal siteId="s-1" product={product} onClose={() => {}} onUpdated={() => {}} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Couldn’t load the stock history')
    expect(screen.queryByText('No stock changes yet.')).not.toBeInTheDocument()
    api.get.mockResolvedValueOnce([{
      id: 'a-1', product_id: 'p-1', option_id: 'opt-1', delta: -1, balance_after: 1,
      reason: 'sale', note: null, created_at: '2026-10-06T10:00:00Z',
    }])
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    // A variant's row names the variant.
    expect(await screen.findByText('sale · Colour: Blue')).toBeInTheDocument()
  })
})

describe('StripeConnectCard — the fee is the plan’s', () => {
  it.each([
    [150, 'Gummfit takes 1.5%'],
    [0, 'Gummfit takes no platform fee on your plan'],
    [null, 'Gummfit takes your plan’s platform fee'],
  ])('states %s bps as "%s"', async (bps, text) => {
    api.get.mockResolvedValueOnce({ connected: true, charges_enabled: true, details_submitted: true, platform_fee_bps: bps })
    render(<StripeConnectCard />)
    await waitFor(() => expect(screen.getByText(/Card payments active/)).toHaveTextContent(text))
    expect(screen.queryByText(/2%/)).not.toBeInTheDocument()
  })
})
