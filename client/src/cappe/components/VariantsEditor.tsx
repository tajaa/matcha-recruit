import type { ComboPart, VariantRow } from '../utils/variants'
import { EMPTY_VARIANT, MAX_VARIANTS, comboKey } from '../utils/variants'

const input = 'w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500'

// Stock, SKU and price for each combination of a product's required pick-one
// groups. Off, a product's options keep their own stock as they always have;
// on, each combination ("M / Red") has its own.
export default function VariantsEditor({ combos, tooMany, rows, onRow, enabled, onEnabled, currency }: {
  combos: ComboPart[][]
  tooMany: boolean
  rows: Record<string, VariantRow>
  onRow: (key: string, row: VariantRow) => void
  enabled: boolean
  onEnabled: (on: boolean) => void
  currency: string
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
      <label className="flex items-start gap-2 text-sm text-zinc-300">
        <input type="checkbox" checked={enabled} onChange={(e) => onEnabled(e.target.checked)} className="mt-0.5 h-4 w-4 rounded border-zinc-600 bg-zinc-950 text-emerald-500" />
        <span>
          Track each combination separately
          <span className="block text-xs text-zinc-500">
            Stock, SKU and price for every mix of your required pick-one groups — &ldquo;Medium / Red&rdquo; has its own count.
          </span>
        </span>
      </label>
      {enabled && (tooMany ? (
        <p className="mt-2 text-xs text-amber-400">That makes more than {MAX_VARIANTS} combinations. Remove some options, or make a group optional.</p>
      ) : combos.length === 0 ? (
        <p className="mt-2 text-xs text-zinc-500">Add an option group, set it to &ldquo;Pick one&rdquo; and tick &ldquo;req&rdquo; — each combination of those groups gets a row here.</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-zinc-500">
                <th className="pb-1.5 pr-2 font-medium">Combination</th>
                <th className="pb-1.5 pr-2 font-medium">SKU</th>
                <th className="pb-1.5 pr-2 font-medium">Price ({currency})</th>
                <th className="pb-1.5 pr-2 font-medium">Stock</th>
                <th className="pb-1.5 font-medium">Sell</th>
              </tr>
            </thead>
            <tbody>
              {combos.map((combo) => {
                const key = comboKey(combo.map((p) => p.key))
                const row = rows[key] || EMPTY_VARIANT
                const label = combo.map((p) => p.option).join(' / ')
                return (
                  <tr key={key} className={row.active ? '' : 'opacity-50'}>
                    <td className="py-1 pr-2 text-zinc-200">{label}</td>
                    <td className="py-1 pr-2"><input value={row.sku} onChange={(e) => onRow(key, { ...row, sku: e.target.value })} placeholder="optional" maxLength={120} aria-label={`SKU for ${label}`} className={input} /></td>
                    <td className="py-1 pr-2"><input value={row.price} onChange={(e) => onRow(key, { ...row, price: e.target.value })} placeholder="from options" inputMode="decimal" aria-label={`Price for ${label}`} className={input} /></td>
                    <td className="py-1 pr-2"><input value={row.stock} onChange={(e) => onRow(key, { ...row, stock: e.target.value })} placeholder="unlimited" type="number" min="0" aria-label={`Stock for ${label}`} className={input} /></td>
                    <td className="py-1"><input type="checkbox" checked={row.active} onChange={(e) => onRow(key, { ...row, active: e.target.checked })} aria-label={`Sell ${label}`} className="h-4 w-4 rounded border-zinc-600 bg-zinc-950 text-emerald-500" /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-zinc-500">A blank price is the product price plus the options&apos; changes. Untick &ldquo;Sell&rdquo; for a combination you don&apos;t make.</p>
        </div>
      ))}
    </div>
  )
}
