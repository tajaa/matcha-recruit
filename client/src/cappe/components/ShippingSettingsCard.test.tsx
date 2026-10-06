import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ShippingSettingsCard from './ShippingSettingsCard'
import type { CappeShippingZones } from '../types'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api }))

const SITE = {
  home_country: 'US', currency: 'USD', shipping_flat_cents: 600,
  shipping_free_threshold_cents: 5000, shipping_label: 'Shipping',
}
const zonesView = (patch: Partial<CappeShippingZones> = {}): CappeShippingZones => ({
  enabled: true, home_country: 'US', currency: 'USD', countries: ['CA', 'FR', 'MX', 'US'], zones: [], ...patch,
})
const NA = {
  id: 'z-1', sort_order: 0, name: 'North America', countries: ['CA'], rest_of_world: false,
  flat_cents: 1500, free_threshold_cents: null, charge_tax: false,
}

function load(zones: CappeShippingZones, site = SITE) {
  api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/shipping-zones') ? zones : site))
  api.put.mockResolvedValue({})
}

function renderCard(onCurrencyChange?: (c: string) => void) {
  render(<MemoryRouter><ShippingSettingsCard siteId="s-1" onCurrencyChange={onCurrencyChange} /></MemoryRouter>)
  return screen.findByRole('button', { name: /Save/ })
}

beforeEach(() => {
  api.get.mockReset()
  api.put.mockReset()
})
afterEach(() => vi.restoreAllMocks())

describe('ShippingSettingsCard — zones', () => {
  it('saves the store first, then the zones it priced against', async () => {
    load(zonesView({ zones: [NA] }))
    fireEvent.click(await renderCard())
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
    expect(api.put.mock.calls[0][0]).toBe('/sites/s-1')
    expect(api.put.mock.calls[0][1]).toMatchObject({ home_country: 'US', currency: 'USD', shipping_flat_cents: 600 })
    expect(api.put.mock.calls[1]).toEqual(['/sites/s-1/shipping-zones', { zones: [{
      name: 'North America', countries: ['CA'], rest_of_world: false,
      flat_cents: 1500, free_threshold_cents: null, charge_tax: false,
    }] }])
  })

  it('adds a zone with a country, a rate and tax', async () => {
    load(zonesView())
    const save = await renderCard()
    fireEvent.click(screen.getByRole('button', { name: /Add a zone/ }))
    const zone = screen.getByRole('group')
    fireEvent.change(within(zone).getByLabelText('Zone name'), { target: { value: 'Europe' } })
    fireEvent.change(within(zone).getByLabelText(/Add a country/), { target: { value: 'FR' } })
    const [rate] = within(zone).getAllByLabelText(/Flat rate/)
    fireEvent.change(rate, { target: { value: '25' } })
    fireEvent.click(within(zone).getByLabelText(/Charge my tax rate/))
    // The home country is never offered for a zone, nor a country another zone has.
    expect(within(zone).queryByRole('option', { name: 'United States' })).not.toBeInTheDocument()
    fireEvent.click(save)
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
    expect(api.put.mock.calls[1][1]).toEqual({ zones: [{
      name: 'Europe', countries: ['FR'], rest_of_world: false,
      flat_cents: 2500, free_threshold_cents: null, charge_tax: true,
    }] })
  })

  it('refuses a zone with no country before sending anything', async () => {
    load(zonesView())
    const save = await renderCard()
    fireEvent.click(screen.getByRole('button', { name: /Add a zone/ }))
    fireEvent.click(save)
    expect(await screen.findByRole('alert')).toHaveTextContent('Add a country to “International”')
    expect(api.put).not.toHaveBeenCalled()
  })

  it('refuses a zone that names the store’s new home country', async () => {
    load(zonesView({ zones: [NA] }))
    const save = await renderCard()
    fireEvent.change(screen.getByLabelText(/Your store is in/), { target: { value: 'CA' } })
    fireEvent.click(save)
    expect(await screen.findByRole('alert')).toHaveTextContent('is your store’s country')
    expect(api.put).not.toHaveBeenCalled()
  })

  it('offers the plan, and saves no zones, when the plan has none', async () => {
    load(zonesView({ enabled: false }))
    fireEvent.click(await renderCard())
    expect(screen.getByRole('link', { name: 'See plans' })).toHaveAttribute('href', '/cappe/billing')
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))
    expect(api.put.mock.calls[0][0]).toBe('/sites/s-1')
  })

  it('shows zones a downgrade paused, and can clear them', async () => {
    load(zonesView({ enabled: false, zones: [NA] }))
    const save = await renderCard()
    expect(screen.getByText(/these zones are paused/)).toHaveTextContent('North America')
    fireEvent.click(screen.getByRole('button', { name: 'Remove them' }))
    fireEvent.click(save)
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
    expect(api.put.mock.calls[1]).toEqual(['/sites/s-1/shipping-zones', { zones: [] }])
  })
})

describe('ShippingSettingsCard — currency', () => {
  it('asks before switching, then tells the page', async () => {
    load(zonesView())
    const onCurrency = vi.fn()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const save = await renderCard(onCurrency)
    expect(onCurrency).toHaveBeenLastCalledWith('USD')
    fireEvent.change(screen.getByLabelText(/Prices are in/), { target: { value: 'EUR' } })
    expect(screen.getByText(/review your prices after saving/)).toBeInTheDocument()
    expect(screen.getAllByText(/\(EUR\)/).length).toBeGreaterThan(0)
    fireEvent.click(save)
    await waitFor(() => expect(onCurrency).toHaveBeenLastCalledWith('EUR'))
    expect(confirm).toHaveBeenCalled()
    expect(api.put.mock.calls[0][1]).toMatchObject({ currency: 'EUR' })
  })

  it('sends nothing when the switch is not confirmed', async () => {
    load(zonesView())
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const save = await renderCard()
    fireEvent.change(screen.getByLabelText(/Prices are in/), { target: { value: 'GBP' } })
    fireEvent.click(save)
    expect(api.put).not.toHaveBeenCalled()
  })

  it('shows why the server refused the switch', async () => {
    load(zonesView())
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    api.put.mockRejectedValueOnce(new Error('2 subscriptions are still billing in the current currency.'))
    const save = await renderCard()
    fireEvent.change(screen.getByLabelText(/Prices are in/), { target: { value: 'CAD' } })
    fireEvent.click(save)
    expect(await screen.findByRole('alert')).toHaveTextContent('2 subscriptions are still billing')
  })
})
