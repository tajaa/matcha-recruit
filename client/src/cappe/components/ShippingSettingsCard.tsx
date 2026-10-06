import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, Check, Truck, Plus, X } from 'lucide-react'
import { cappeApi } from '../api'
import { parseMoneyCents } from '../utils/money'
import { STORE_CURRENCIES, countryName } from '../utils/countries'
import { BILLING_PATH } from '../pages/CappeBilling/paths'
import type { CappeShippingZoneInput, CappeShippingZones, CappeSite } from '../types'

// Where the store is based, what it charges in, and where it ships.
//
// The home country's rates are the store's own (flat rate, free-over
// threshold, and its tax rate from the Tax card). Zones add other countries,
// each with its own rates; without any, the store ships within its home country
// only — Stripe's payment page then accepts an address there and nowhere else.
// The buyer picks the country in the bag and is priced for it.

type ZoneRow = { key: number; name: string; countries: string[]; rest: boolean; flat: string; freeOver: string; tax: boolean }

let nextKey = 0
const dollars = (cents: number | null | undefined) => (cents ? (cents / 100).toString() : '')
const field = 'mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-lime-500'

export default function ShippingSettingsCard({ siteId, onCurrencyChange }: {
  siteId: string
  /** Called with the store's currency once loaded, and again when it changes. */
  onCurrencyChange?: (currency: string) => void
}) {
  const [home, setHome] = useState('US')
  const [currency, setCurrency] = useState('USD')
  const [savedCurrency, setSavedCurrency] = useState('USD')
  const [flat, setFlat] = useState('') // as typed
  const [freeOver, setFreeOver] = useState('') // '' = no threshold
  const [label, setLabel] = useState('Shipping')
  const [zones, setZones] = useState<ZoneRow[]>([])
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
      setHome(s.home_country || z.home_country || 'US')
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
    rest: false, flat: '', freeOver: '', tax: false,
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
      out.push({
        name, countries: z.rest ? [] : z.countries, rest_of_world: z.rest,
        flat_cents: flatCents, free_threshold_cents: freeCents, charge_tax: z.tax,
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
    const sendZones = zonesEnabled || zonesCleared
    const bodies = sendZones ? zoneBodies() : []
    if (typeof bodies === 'string') { setError(bodies); return }
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
      })
      if (currency !== savedCurrency) {
        setSavedCurrency(currency)
        onCurrencyChange?.(currency)
      }
      if (sendZones) {
        await cappeApi.put(`/sites/${siteId}/shipping-zones`, { zones: bodies })
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

      <div className="mt-4 text-xs font-medium uppercase tracking-wide text-zinc-500">Other countries</div>
      {!zonesEnabled && zones.length === 0 && (
        <p className="mt-1 text-xs text-zinc-400">
          You ship within {homeName} only. Shipping to other countries comes with the Business plan and up.{' '}
          <Link to={BILLING_PATH} className="text-lime-400 hover:underline">See plans</Link>
        </p>
      )}
      {!zonesEnabled && zones.length > 0 && (
        <div className="mt-1 text-xs text-amber-300">
          Your plan doesn’t include shipping to other countries, so these zones are paused and you ship within {homeName} only:
          {' '}{zones.map((z) => z.name).join(', ')}.{' '}
          <button type="button" onClick={() => { setZones([]); setZonesCleared(true) }} className="underline hover:text-amber-200">Remove them</button>
          {' '}or <Link to={BILLING_PATH} className="underline hover:text-amber-200">upgrade</Link>.
        </div>
      )}
      {!zonesEnabled && zonesCleared && (
        <p className="mt-1 text-xs text-zinc-400">The paused zones will be removed when you save.</p>
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
                  Charge my tax rate here
                </label>
              </div>
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
        <span className="ml-auto text-[11px] text-zinc-500">Once per order with a physical item. The buyer picks the country in their bag; tax is charged within {homeName} and in zones where you turn it on.</span>
      </div>
    </div>
  )
}
