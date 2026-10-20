import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, Check, Truck, Plus, X } from 'lucide-react'
import { cappeApi } from '../api'
import { parseMoneyCents, parsePercentBps } from '../utils/money'
import { STORE_CURRENCIES, countryName } from '../utils/countries'
import { weightUnit, type WeightUnit } from '../utils/weight'
import { BILLING_PATH } from '../pages/CappeBilling/paths'
import DeliveryOptionsEditor from './DeliveryOptionsEditor'
import { rateBodies, rateRow, type RateRow } from '../utils/deliveryOptions'
import type { CappeShippingRateInput, CappeShippingZoneInput, CappeShippingZones, CappeSite } from '../types'

// Where the store is based, what it charges in, and where it ships.
//
// The home country's rates are the store's own (flat rate, free-over
// threshold, and its tax rate from the Tax card). Zones add other countries,
// each with its own rates; without any, the store ships within its home country
// only — Stripe's payment page then accepts an address there and nowhere else.
// The buyer picks the country in the bag and is priced for it.
//
// Every destination may also have delivery options (DeliveryOptionsEditor):
// pickup, local delivery, express… The bag offers them; without any, the
// destination's flat rate is the one option. They come with zones' plan.

type ZoneRow = {
  key: number; name: string; countries: string[]; rest: boolean; flat: string; freeOver: string; tax: boolean
  /** The zone's own tax rate, percent as typed; '' = the store's rate. */
  taxRate: string
  rates: RateRow[]
}

let nextKey = 0
const dollars = (cents: number | null | undefined) => (cents ? (cents / 100).toString() : '')
const field = 'mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-lime-500'

export default function ShippingSettingsCard({ siteId, onCurrencyChange, onHomeCountryChange }: {
  siteId: string
  /** Called with the store's currency once loaded, and again when it changes. */
  onCurrencyChange?: (currency: string) => void
  /** Called with the store's country once loaded and after a save (it sets the weight unit). */
  onHomeCountryChange?: (country: string) => void
}) {
  const [home, setHome] = useState('US')
  const [currency, setCurrency] = useState('USD')
  const [savedCurrency, setSavedCurrency] = useState('USD')
  const [flat, setFlat] = useState('') // as typed
  const [freeOver, setFreeOver] = useState('') // '' = no threshold
  const [label, setLabel] = useState('Shipping')
  const [zones, setZones] = useState<ZoneRow[]>([])
  const [homeRates, setHomeRates] = useState<RateRow[]>([])
  const [handlingMin, setHandlingMin] = useState('')
  const [handlingMax, setHandlingMax] = useState('')
  // Weights are typed in the unit of the country the store was in when this
  // loaded, so a country change before saving can't re-read them.
  const [unit, setUnit] = useState<WeightUnit>('lb')
  const [zonesEnabled, setZonesEnabled] = useState(false)
  const [zonesCleared, setZonesCleared] = useState(false)
  const [countries, setCountries] = useState<string[]>([])
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // A failed load must not fall through to the form: its blank boxes, saved,
  // would write zeros over the store's real settings.
  const [loadError, setLoadError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    Promise.all([
      cappeApi.get<CappeSite>(`/sites/${siteId}`),
      cappeApi.get<CappeShippingZones>(`/sites/${siteId}/shipping-zones`),
    ]).then(([s, z]) => {
      const country = s.home_country || z.home_country || 'US'
      const u = weightUnit(country)
      setHome(country)
      setUnit(u)
      onHomeCountryChange?.(country)
      setHandlingMin(s.handling_days_min != null ? String(s.handling_days_min) : '')
      setHandlingMax(s.handling_days_max != null ? String(s.handling_days_max) : '')
      setHomeRates((z.home_rates || []).map((r) => rateRow(r, u)))
      setCurrency(s.currency || 'USD')
      setSavedCurrency(s.currency || 'USD')
      onCurrencyChange?.(s.currency || 'USD')
      setFlat(dollars(s.shipping_flat_cents))
      setFreeOver(s.shipping_free_threshold_cents != null ? (s.shipping_free_threshold_cents / 100).toString() : '')
      setLabel(s.shipping_label || 'Shipping')
      setZonesEnabled(z.enabled)
      setCountries(z.countries)
      setZones(z.zones.map((zone) => ({
        key: nextKey++, name: zone.name, countries: zone.countries, rest: zone.rest_of_world,
        flat: dollars(zone.flat_cents),
        freeOver: zone.free_threshold_cents != null ? (zone.free_threshold_cents / 100).toString() : '',
        tax: zone.charge_tax,
        taxRate: zone.tax_rate_bps != null ? String(zone.tax_rate_bps / 100) : '',
        rates: (zone.rates || []).map((r) => rateRow(r, u)),
      })))
      setLoaded(true)
    }).catch((e) => setLoadError(e instanceof Error ? e.message : 'Could not load these settings'))
    // onCurrencyChange is a notification, not an input: re-loading when a
    // parent re-renders with a new function would discard unsaved edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, attempt])

  const setZone = (key: number, patch: Partial<ZoneRow>) =>
    setZones((zs) => zs.map((z) => (z.key === key ? { ...z, ...patch } : z)))
  const addZone = () => setZones((zs) => [...zs, {
    key: nextKey++, name: zs.length ? `Zone ${zs.length + 1}` : 'International', countries: [],
    rest: false, flat: '', freeOver: '', tax: false, taxRate: '', rates: [],
  }])
  // A country is in one zone at most, and never the home country.
  const taken = new Set(zones.flatMap((z) => z.countries))

  function zoneBodies(): CappeShippingZoneInput[] | string {
    const out: CappeShippingZoneInput[] = []
    if (zones.filter((z) => z.rest).length > 1) return 'Only one zone can cover everywhere else.'
    for (const z of zones) {
      const name = z.name.trim()
      if (!name) return 'Give every zone a name.'
      if (!z.rest && !z.countries.length) return `Add a country to “${name}”, or make it cover everywhere else.`
      if (!z.rest && z.countries.includes(home)) {
        return `${countryName(home)} is your store’s country — its rates are the ones above. Remove it from “${name}”.`
      }
      const flatCents = z.flat.trim() === '' ? 0 : parseMoneyCents(z.flat)
      if (flatCents === null) return `Enter the rate for “${name}” as a plain amount, e.g. 15`
      const freeCents = z.freeOver.trim() === '' ? null : parseMoneyCents(z.freeOver)
      if (z.freeOver.trim() !== '' && freeCents === null) return `Enter the free-shipping amount for “${name}” as a plain amount, e.g. 100`
      const rates = rateBodies(z.rates, unit)
      if (typeof rates === 'string') return rates
      const taxBps = z.tax && z.taxRate.trim() !== '' ? parsePercentBps(z.taxRate) : null
      if (z.tax && z.taxRate.trim() !== '' && (taxBps === null || taxBps > 10000)) {
        return `Enter the tax rate for “${name}” as a plain number, e.g. 20 (or leave it blank for your own rate)`
      }
      out.push({
        name, countries: z.rest ? [] : z.countries, rest_of_world: z.rest,
        flat_cents: flatCents, free_threshold_cents: freeCents, charge_tax: z.tax, tax_rate_bps: taxBps, rates,
      })
    }
    return out
  }

  async function save() {
    setError(null); setSaved(false)
    // Refuse an amount we can't read rather than silently charging $0 shipping
    // (parseFloat('1,299') is 1) — see utils/money.ts.
    const flatCents = flat.trim() === '' ? 0 : parseMoneyCents(flat)
    if (flatCents === null) { setError('Enter the flat rate as a plain amount, e.g. 6 or 6.50'); return }
    const freeCents = freeOver.trim() === '' ? null : parseMoneyCents(freeOver)
    if (freeOver.trim() !== '' && freeCents === null) {
      setError('Enter the free-shipping threshold as a plain amount, e.g. 50')
      return
    }
    const handling = [handlingMin, handlingMax].map((t) => (t.trim() === '' ? null : Number(t)))
    if (handling.some((d) => d !== null && !(Number.isInteger(d) && d >= 0 && d <= 60))) {
      setError('Enter the handling time in whole business days (0–60).')
      return
    }
    if (handling[0] !== null && handling[1] !== null && handling[0] > handling[1]) {
      setError('The handling time’s first number is above its second.')
      return
    }
    const sendZones = zonesEnabled || zonesCleared
    const bodies = sendZones ? zoneBodies() : []
    if (typeof bodies === 'string') { setError(bodies); return }
    const homeBodies: CappeShippingRateInput[] | string = sendZones ? rateBodies(homeRates, unit) : []
    if (typeof homeBodies === 'string') { setError(homeBodies); return }
    if (currency !== savedCurrency && !window.confirm(
      `Charge in ${currency} from now on? Every product keeps its number — a ${savedCurrency} 20 price becomes ${currency} 20 — `
      + 'so review your prices after switching. Orders already placed keep their currency.',
    )) return
    setSaving(true)
    try {
      // The store first: zones are checked against its home country.
      await cappeApi.put(`/sites/${siteId}`, {
        home_country: home,
        currency,
        shipping_flat_cents: Math.max(0, flatCents),
        shipping_free_threshold_cents: freeCents === null ? null : Math.max(0, freeCents),
        shipping_label: label.trim() || 'Shipping',
        handling_days_min: handling[0],
        handling_days_max: handling[1],
      })
      onHomeCountryChange?.(home)
      if (currency !== savedCurrency) {
        setSavedCurrency(currency)
        onCurrencyChange?.(currency)
      }
      if (sendZones) {
        await cappeApi.put(`/sites/${siteId}/shipping-zones`, { zones: bodies, home_rates: homeBodies })
        setZonesCleared(false)
      }
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  if (loadError) {
    return (
      <div role="alert" className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">
        Couldn’t load your shipping settings, so they can’t be edited right now. {loadError}
        <button onClick={() => { setLoadError(null); setAttempt((n) => n + 1) }} className="rounded-lg border border-red-500/40 px-2.5 py-1 text-xs font-medium hover:bg-red-500/10">Try again</button>
      </div>
    )
  }
  if (!loaded) return null

  const homeName = countryName(home)
  return (
    <div className="mb-5 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-zinc-200">
        <Truck className="h-4 w-4 text-lime-400" /> Shipping &amp; currency
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="text-xs text-zinc-400">
          Your store is in
          <select value={home} onChange={(e) => setHome(e.target.value)} className={field}>
            {countries.map((c) => <option key={c} value={c}>{countryName(c)}</option>)}
          </select>
        </label>
        <label className="text-xs text-zinc-400">
          Prices are in
          <select value={currency} onChange={(e) => setCurrency(e.target.value)} className={field}>
            {STORE_CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      </div>
      {currency !== savedCurrency && (
        <p className="mt-2 text-xs text-amber-300">
          Products keep their numbers when you switch — review your prices after saving.
        </p>
      )}

      <div className="mt-4 text-xs font-medium uppercase tracking-wide text-zinc-500">Within {homeName}</div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="text-xs text-zinc-400">
          Flat rate ({currency})
          <input value={flat} onChange={(e) => setFlat(e.target.value)} inputMode="decimal" placeholder="0" className={field} />
        </label>
        <label className="text-xs text-zinc-400">
          Free over ({currency})
          <input value={freeOver} onChange={(e) => setFreeOver(e.target.value)} inputMode="decimal" placeholder="No threshold" className={field} />
        </label>
        <label className="text-xs text-zinc-400">
          Label
          <input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={40} placeholder="Shipping" className={field} />
        </label>
      </div>
      <label className="mt-3 block text-xs text-zinc-400">
        Handling time — business days to get an order out of the door (shown to buyers with each delivery estimate)
        <span className="mt-1 flex max-w-[14rem] items-center gap-1">
          <input value={handlingMin} onChange={(e) => setHandlingMin(e.target.value)} inputMode="numeric" placeholder="1" aria-label="Fewest handling days" className={`${field} mt-0`} />
          –
          <input value={handlingMax} onChange={(e) => setHandlingMax(e.target.value)} inputMode="numeric" placeholder="2" aria-label="Most handling days" className={`${field} mt-0`} />
        </span>
      </label>
      {zonesEnabled && (
        <>
          <div className="mt-4 text-xs font-medium uppercase tracking-wide text-zinc-500">Delivery options within {homeName}</div>
          <DeliveryOptionsEditor rows={homeRates} onChange={setHomeRates} currency={currency} unit={unit}
            flatLabel={`the flat rate above (“${label.trim() || 'Shipping'}”)`} />
        </>
      )}

      <div className="mt-4 text-xs font-medium uppercase tracking-wide text-zinc-500">Other countries</div>
      {!zonesEnabled && zones.length === 0 && homeRates.length === 0 && (
        <p className="mt-1 text-xs text-zinc-400">
          You ship within {homeName} only, at one flat rate. Shipping to other countries, and offering pickup, local
          delivery or faster shipping, come with the Business plan and up.{' '}
          <Link to={BILLING_PATH} className="text-lime-400 hover:underline">See plans</Link>
        </p>
      )}
      {!zonesEnabled && (zones.length > 0 || homeRates.length > 0) && (
        <div className="mt-1 text-xs text-amber-300">
          Your plan doesn’t include shipping zones or delivery options, so these are paused and buyers in {homeName} get
          your flat rate only:
          {' '}{[...zones.map((z) => z.name), ...homeRates.map((r) => r.name)].join(', ')}.{' '}
          <button type="button" onClick={() => { setZones([]); setHomeRates([]); setZonesCleared(true) }} className="underline hover:text-amber-200">Remove them</button>
          {' '}or <Link to={BILLING_PATH} className="underline hover:text-amber-200">upgrade</Link>.
        </div>
      )}
      {!zonesEnabled && zonesCleared && (
        <p className="mt-1 text-xs text-zinc-400">The paused zones and options will be removed when you save.</p>
      )}
      {zonesEnabled && (
        <div className="mt-2 space-y-3">
          {zones.length === 0 && <p className="text-xs text-zinc-400">You ship within {homeName} only. Add a zone to ship elsewhere.</p>}
          {zones.map((z) => (
            <fieldset key={z.key} className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3">
              <legend className="sr-only">{z.name || 'Shipping zone'}</legend>
              <div className="flex items-center gap-2">
                <input value={z.name} onChange={(e) => setZone(z.key, { name: e.target.value })} maxLength={80} aria-label="Zone name" placeholder="Zone name, e.g. Europe" className={`${field} mt-0 flex-1`} />
                <button type="button" onClick={() => setZones((zs) => zs.filter((x) => x.key !== z.key))} aria-label={`Remove ${z.name || 'zone'}`} className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <label className="mt-2 flex items-center gap-2 text-xs text-zinc-300">
                <input type="checkbox" checked={z.rest} onChange={(e) => setZone(z.key, { rest: e.target.checked })}
                  disabled={!z.rest && zones.some((x) => x.rest)} />
                Everywhere else — every country not in another zone
              </label>
              {!z.rest && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {z.countries.map((c) => (
                    <span key={c} className="flex items-center gap-1 rounded-full bg-zinc-800 px-2 py-0.5 text-xs text-zinc-200">
                      {countryName(c)}
                      <button type="button" onClick={() => setZone(z.key, { countries: z.countries.filter((x) => x !== c) })} aria-label={`Remove ${countryName(c)}`} className="text-zinc-500 hover:text-zinc-200">
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                  <select value="" aria-label={`Add a country to ${z.name || 'this zone'}`}
                    onChange={(e) => { if (e.target.value) setZone(z.key, { countries: [...z.countries, e.target.value] }) }}
                    className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-300">
                    <option value="">Add a country…</option>
                    {countries.filter((c) => c !== home && !taken.has(c)).map((c) => <option key={c} value={c}>{countryName(c)}</option>)}
                  </select>
                </div>
              )}
              <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
                <label className="text-xs text-zinc-400">
                  Flat rate ({currency})
                  <input value={z.flat} onChange={(e) => setZone(z.key, { flat: e.target.value })} inputMode="decimal" placeholder="0" className={field} />
                </label>
                <label className="text-xs text-zinc-400">
                  Free over ({currency})
                  <input value={z.freeOver} onChange={(e) => setZone(z.key, { freeOver: e.target.value })} inputMode="decimal" placeholder="No threshold" className={field} />
                </label>
                <label className="flex items-end gap-2 pb-2 text-xs text-zinc-300">
                  <input type="checkbox" checked={z.tax} onChange={(e) => setZone(z.key, { tax: e.target.checked })} />
                  Charge tax here
                </label>
              </div>
              {z.tax && (
                <label className="mt-2 block max-w-xs text-xs text-zinc-400">
                  Tax rate here (%)
                  <input value={z.taxRate} onChange={(e) => setZone(z.key, { taxRate: e.target.value })} inputMode="decimal"
                    placeholder="Blank = your own rate" aria-label={`Tax rate for ${z.name || 'this zone'}`} className={field} />
                </label>
              )}
              <div className="mt-3 text-[11px] font-medium uppercase tracking-wide text-zinc-500">Delivery options</div>
              <DeliveryOptionsEditor rows={z.rates} onChange={(rates) => setZone(z.key, { rates })} currency={currency} unit={unit}
                flatLabel="this zone’s flat rate" />
            </fieldset>
          ))}
          {zones.length < 20 && (
            <button type="button" onClick={addZone} className="flex items-center gap-1 text-xs font-medium text-lime-400 hover:text-lime-300">
              <Plus className="h-3.5 w-3.5" /> Add a zone
            </button>
          )}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="flex items-center gap-1.5 rounded-lg bg-zinc-100 px-3 py-1.5 text-sm font-semibold text-zinc-900 hover:bg-white disabled:opacity-60"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Save
        </button>
        {saved && <span className="text-xs text-lime-400">Saved</span>}
        {error && <span role="alert" className="text-xs text-red-400">{error}</span>}
        <span className="ml-auto text-[11px] text-zinc-500">Once per order with a physical item. The buyer picks the country and the delivery option in their bag; tax is charged within {homeName} and in zones where you turn it on.</span>
      </div>
    </div>
  )
}
