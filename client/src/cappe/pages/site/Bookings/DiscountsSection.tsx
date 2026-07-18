import type { Dispatch, SetStateAction } from 'react'
import { Loader2, Trash2, Save, Percent } from 'lucide-react'
import type { CappeBookingType, CappeDiscount, CappeProduct } from '../../../types'
import { inputCls } from './constants'

interface DiscountsSectionProps {
  discounts: CappeDiscount[]
  setDiscounts: Dispatch<SetStateAction<CappeDiscount[]>>
  setDiscount: (i: number, patch: Partial<CappeDiscount>) => void
  types: CappeBookingType[]
  products: CappeProduct[]
  addDiscount: () => void
  saveDiscounts: () => void
  savingDiscounts: boolean
}

export function DiscountsSection({
  discounts, setDiscounts, setDiscount, types, products, addDiscount, saveDiscounts, savingDiscounts,
}: DiscountsSectionProps) {
  return (
    <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
      <h2 className="flex items-center gap-1.5 text-sm font-semibold text-zinc-100"><Percent className="h-4 w-4 text-emerald-400" /> Discounts</h2>
      <p className="mb-3 mt-1 text-xs text-zinc-500">
        Quiet week? Drop a discount across <span className="text-zinc-300">all offerings</span> or a single service/product.
        Leave dates blank to run until you turn it off. The best single discount applies — they don't stack.
      </p>
      <div className="space-y-2">
        {discounts.map((d, i) => {
          const targetValue = d.scope === 'all' ? 'all' : `${d.scope === 'booking_type' ? 'bt' : 'pr'}:${d.target_id ?? ''}`
          return (
            <div key={d.id} className="flex flex-wrap items-center gap-2">
              <input value={d.label} onChange={(e) => setDiscount(i, { label: e.target.value })} placeholder="Label (e.g. Slow-week special)" className={`w-44 ${inputCls}`} />
              <div className="flex items-center gap-1">
                <input type="number" min="1" max="90" value={d.percent_off} onChange={(e) => setDiscount(i, { percent_off: parseInt(e.target.value, 10) || 0 })} className={`w-16 ${inputCls}`} />
                <span className="text-sm text-zinc-400">% off</span>
              </div>
              <select
                value={targetValue}
                onChange={(e) => {
                  const v = e.target.value
                  if (v === 'all') setDiscount(i, { scope: 'all', target_id: null })
                  else if (v.startsWith('bt:')) setDiscount(i, { scope: 'booking_type', target_id: v.slice(3) })
                  else setDiscount(i, { scope: 'product', target_id: v.slice(3) })
                }}
                className={inputCls}
              >
                <option value="all">All offerings</option>
                {types.length > 0 && (
                  <optgroup label="Services">
                    {types.map((t) => <option key={t.id} value={`bt:${t.id}`}>{t.name}</option>)}
                  </optgroup>
                )}
                {products.length > 0 && (
                  <optgroup label="Products">
                    {products.map((p) => <option key={p.id} value={`pr:${p.id}`}>{p.name}</option>)}
                  </optgroup>
                )}
              </select>
              <label className="flex items-center gap-1 text-xs text-zinc-400" title="Start date (optional)">
                <span className="text-zinc-500">from</span>
                <input type="date" value={d.starts_on ?? ''} onChange={(e) => setDiscount(i, { starts_on: e.target.value || null })} className={inputCls} />
              </label>
              <label className="flex items-center gap-1 text-xs text-zinc-400" title="End date (optional)">
                <span className="text-zinc-500">to</span>
                <input type="date" value={d.ends_on ?? ''} onChange={(e) => setDiscount(i, { ends_on: e.target.value || null })} className={inputCls} />
              </label>
              <label className="flex items-center gap-1.5 text-xs text-zinc-400">
                <input type="checkbox" checked={d.active} onChange={(e) => setDiscount(i, { active: e.target.checked })} className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-950 text-emerald-500" />
                Active
              </label>
              <button type="button" onClick={() => setDiscounts((ds) => ds.filter((_, idx) => idx !== i))} className="text-zinc-400 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
            </div>
          )
        })}
        {discounts.length === 0 && <p className="text-sm text-zinc-400">No discounts running.</p>}
      </div>
      <div className="mt-3 flex gap-2">
        <button onClick={addDiscount} className="text-xs font-medium text-emerald-400 hover:underline">+ Add discount</button>
        <button onClick={saveDiscounts} disabled={savingDiscounts} className="ml-auto flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">
          {savingDiscounts ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save discounts
        </button>
      </div>
    </section>
  )
}
