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
  enabled: true, home_country: 'US', currency: 'USD', countries: ['CA', 'FR', 'MX', 'US'], zones: [], home_rates: [], ...patch,
})
const NA = {
  id: 'z-1', sort_order: 0, name: 'North America', countries: ['CA'], rest_of_world: false,
  flat_cents: 1500, free_threshold_cents: null, charge_tax: false, rates: [],
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
      flat_cents: 1500, free_threshold_cents: null, charge_tax: false, tax_rate_bps: null, rates: [],
    }], home_rates: [] }])
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
    fireEvent.click(within(zone).getByLabelText(/Charge tax here/))
    // The home country is never offered for a zone, nor a country another zone has.
    expect(within(zone).queryByRole('option', { name: 'United States' })).not.toBeInTheDocument()
    fireEvent.click(save)
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
    expect(api.put.mock.calls[1][1]).toEqual({ zones: [{
      name: 'Europe', countries: ['FR'], rest_of_world: false,
      flat_cents: 2500, free_threshold_cents: null, charge_tax: true, tax_rate_bps: null, rates: [],
    }], home_rates: [] })
  })

  it('saves a zone’s own tax rate, and refuses one it can’t read', async () => {
    load(zonesView({ zones: [{ ...NA, charge_tax: true, tax_rate_bps: 500 }] }))
    const save = await renderCard()
    const rate = screen.getByRole('textbox', { name: 'Tax rate for North America' })
    expect(rate).toHaveValue('5')
    fireEvent.change(rate, { target: { value: '1,2,3' } })
    fireEvent.click(save)
    expect(await screen.findByRole('alert')).toHaveTextContent('tax rate for “North America”')
    expect(api.put).not.toHaveBeenCalled()
    fireEvent.change(rate, { target: { value: '13' } })
    fireEvent.click(save)
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
    expect(api.put.mock.calls[1][1].zones[0]).toMatchObject({ charge_tax: true, tax_rate_bps: 1300 })
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
    expect(screen.getByText(/so these are paused/)).toHaveTextContent('North America')
    fireEvent.click(screen.getByRole('button', { name: 'Remove them' }))
    fireEvent.click(save)
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
    expect(api.put.mock.calls[1]).toEqual(['/sites/s-1/shipping-zones', { zones: [], home_rates: [] }])
  })
})

const PICKUP = {
  id: 'r-1', sort_order: 0, name: 'Pickup', method: 'pickup' as const, amount_cents: 0, per_item_cents: 0,
  min_subtotal_cents: null, max_subtotal_cents: null, min_weight_g: null, max_weight_g: null, free_over_cents: null,
  delivery_min_days: 0, delivery_max_days: 1, postal_codes: [], instructions: '12 Market St, 9–5',
}

describe('ShippingSettingsCard — delivery options', () => {
  it('saves the home options and the handling time, and tells the page the store’s country', async () => {
    load(zonesView({ home_rates: [PICKUP] }), { ...SITE, handling_days_min: 1, handling_days_max: 2 } as typeof SITE)
    const onHome = vi.fn()
    render(<MemoryRouter><ShippingSettingsCard siteId="s-1" onHomeCountryChange={onHome} /></MemoryRouter>)
    const save = await screen.findByRole('button', { name: /Save/ })
    expect(onHome).toHaveBeenCalledWith('US')
    expect(screen.getByLabelText('Fewest handling days')).toHaveValue('1')
    fireEvent.click(screen.getByRole('button', { name: /Local delivery/ }))
    const local = screen.getByRole('group', { name: 'Local delivery' })
    fireEvent.change(within(local).getByLabelText(/Price \(USD\)/), { target: { value: '7.50' } })
    fireEvent.change(within(local).getByLabelText(/Postal codes you deliver to/), { target: { value: '94110, 9411 941' } })
    fireEvent.change(screen.getByLabelText('Most handling days'), { target: { value: '3' } })
    fireEvent.click(save)
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
    expect(api.put.mock.calls[0][1]).toMatchObject({ handling_days_min: 1, handling_days_max: 3 })
    const body = api.put.mock.calls[1][1]
    expect(body.home_rates).toEqual([
      expect.objectContaining({ name: 'Pickup', method: 'pickup', instructions: '12 Market St, 9–5', delivery_max_days: 1 }),
      expect.objectContaining({ name: 'Local delivery', method: 'local_delivery', amount_cents: 750, postal_codes: ['94110', '9411', '941'] }),
    ])
  })

  it('makes an option the default by moving it first', async () => {
    load(zonesView({ home_rates: [PICKUP, { ...PICKUP, id: 'r-2', name: 'Express', method: 'ship', instructions: null }] }))
    const save = await renderCard()
    fireEvent.click(screen.getByRole('button', { name: 'Make “Express” the default' }))
    fireEvent.click(save)
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
    expect(api.put.mock.calls[1][1].home_rates.map((r: { name: string }) => r.name)).toEqual(['Express', 'Pickup'])
  })

  it('refuses an option it can’t read before sending anything', async () => {
    load(zonesView())
    const save = await renderCard()
    fireEvent.click(screen.getByRole('button', { name: /Shipping option/ }))
    fireEvent.change(screen.getByLabelText(/Price \(USD\)/), { target: { value: '1,299.00' } })
    fireEvent.click(save)
    expect(await screen.findByRole('alert')).toHaveTextContent('Enter the price for “Standard”')
    expect(api.put).not.toHaveBeenCalled()
  })

  it('refuses a handling time out of order', async () => {
    load(zonesView())
    const save = await renderCard()
    fireEvent.change(screen.getByLabelText('Fewest handling days'), { target: { value: '4' } })
    fireEvent.change(screen.getByLabelText('Most handling days'), { target: { value: '2' } })
    fireEvent.click(save)
    expect(await screen.findByRole('alert')).toHaveTextContent('handling time')
    expect(api.put).not.toHaveBeenCalled()
  })

  it('shows home options a downgrade paused', async () => {
    load(zonesView({ enabled: false, home_rates: [PICKUP] }))
    await renderCard()
    expect(screen.getByText(/so these are paused/)).toHaveTextContent('Pickup')
    expect(screen.queryByRole('button', { name: /Shipping option/ })).not.toBeInTheDocument()
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
