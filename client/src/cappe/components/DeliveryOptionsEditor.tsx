import { ArrowUp, Plus, X } from 'lucide-react'
import { MAX_RATES, METHODS, newRateRow, type RateRow } from '../utils/deliveryOptions'
import type { WeightUnit } from '../utils/weight'
import type { CappeShippingMethod } from '../types'

// One destination's delivery options (server: services/shipping.py). Each is
// shipped, picked up or delivered locally, priced by what is in the bag, and
// the bag offers them in this order — the first is the default. With none,
// the destination's flat rate is the only option, exactly as before.

const field = 'mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-lime-500'

export default function DeliveryOptionsEditor({ rows, onChange, currency, unit, flatLabel }: {
  rows: RateRow[]
  onChange: (rows: RateRow[]) => void
  currency: string
  unit: WeightUnit
  /** What the buyer gets with no options here: the destination's flat rate. */
  flatLabel: string
}) {
  const set = (key: number, patch: Partial<RateRow>) => onChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  const moveUp = (i: number) => onChange([rows[i], ...rows.slice(0, i), ...rows.slice(i + 1)])
  return (
    <div className="mt-2 space-y-2">
      {rows.length === 0 && (
        <p className="text-xs text-zinc-500">Buyers get {flatLabel}. Add options to offer pickup, local delivery or faster shipping.</p>
      )}
      {rows.map((r, i) => (
        <fieldset key={r.key} className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3">
          <legend className="sr-only">{r.name || 'Delivery option'}</legend>
          <div className="flex flex-wrap items-center gap-2">
            <input value={r.name} onChange={(e) => set(r.key, { name: e.target.value })} maxLength={80} aria-label="Option name"
              placeholder="Name, e.g. Express" className={`${field} mt-0 min-w-[10rem] flex-1`} />
            <select value={r.method} aria-label={`How “${r.name || 'this option'}” gets there`}
              onChange={(e) => set(r.key, { method: e.target.value as CappeShippingMethod })}
              className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-2 text-sm text-zinc-200">
              {METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            {i === 0 ? (
              <span className="text-[11px] text-zinc-500">Default</span>
            ) : (
              <button type="button" onClick={() => moveUp(i)} aria-label={`Make “${r.name || 'this option'}” the default`}
                className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"><ArrowUp className="h-4 w-4" /></button>
            )}
            <button type="button" onClick={() => onChange(rows.filter((x) => x.key !== r.key))} aria-label={`Remove ${r.name || 'option'}`}
              className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"><X className="h-4 w-4" /></button>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <label className="text-xs text-zinc-400">
              Price ({currency})
              <input value={r.amount} onChange={(e) => set(r.key, { amount: e.target.value })} inputMode="decimal" placeholder="0" className={field} />
            </label>
            {r.method !== 'pickup' && (
              <label className="text-xs text-zinc-400">
                Each extra item
                <input value={r.perItem} onChange={(e) => set(r.key, { perItem: e.target.value })} inputMode="decimal" placeholder="0" className={field} />
              </label>
            )}
            <label className="text-xs text-zinc-400">
              Free over ({currency})
              <input value={r.freeOver} onChange={(e) => set(r.key, { freeOver: e.target.value })} inputMode="decimal" placeholder="Never" className={field} />
            </label>
            <label className="text-xs text-zinc-400">
              {r.method === 'pickup' ? 'Ready in (days)' : 'Takes (days)'}
              <span className="mt-1 flex items-center gap-1">
                <input value={r.minDays} onChange={(e) => set(r.key, { minDays: e.target.value })} inputMode="numeric" placeholder="2" aria-label="Fewest days" className={`${field} mt-0`} />
                –
                <input value={r.maxDays} onChange={(e) => set(r.key, { maxDays: e.target.value })} inputMode="numeric" placeholder="5" aria-label="Most days" className={`${field} mt-0`} />
              </span>
            </label>
          </div>
          {r.method === 'pickup' && (
            <label className="mt-2 block text-xs text-zinc-400">
              Where and when to collect
              <textarea value={r.instructions} onChange={(e) => set(r.key, { instructions: e.target.value })} maxLength={500} rows={2}
                placeholder="12 Market St, weekdays 9–5. Bring your order number." className={field} />
            </label>
          )}
          {r.method === 'local_delivery' && (
            <label className="mt-2 block text-xs text-zinc-400">
              Postal codes you deliver to (the start of each is enough, e.g. 941). Blank = anywhere here.
              <input value={r.postal} onChange={(e) => set(r.key, { postal: e.target.value })} placeholder="94110, 94114, 9412" className={field} />
            </label>
          )}
          <details className="mt-2 text-xs text-zinc-400">
            <summary className="cursor-pointer text-zinc-500 hover:text-zinc-300">Only offer it for some orders</summary>
            <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <label>Order value from<input value={r.minSubtotal} onChange={(e) => set(r.key, { minSubtotal: e.target.value })} inputMode="decimal" placeholder="Any" className={field} /></label>
              <label>Order value up to<input value={r.maxSubtotal} onChange={(e) => set(r.key, { maxSubtotal: e.target.value })} inputMode="decimal" placeholder="Any" className={field} /></label>
              <label>Weight from ({unit})<input value={r.minWeight} onChange={(e) => set(r.key, { minWeight: e.target.value })} inputMode="decimal" placeholder="Any" className={field} /></label>
              <label>Weight up to ({unit})<input value={r.maxWeight} onChange={(e) => set(r.key, { maxWeight: e.target.value })} inputMode="decimal" placeholder="Any" className={field} /></label>
            </div>
          </details>
        </fieldset>
      ))}
      {rows.length < MAX_RATES && (
        <div className="flex flex-wrap gap-3">
          {METHODS.map((m) => (
            <button key={m.value} type="button" onClick={() => onChange([...rows, newRateRow(m.value)])}
              className="flex items-center gap-1 text-xs font-medium text-lime-400 hover:text-lime-300">
              <Plus className="h-3.5 w-3.5" /> {m.value === 'ship' ? 'Shipping option' : m.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
