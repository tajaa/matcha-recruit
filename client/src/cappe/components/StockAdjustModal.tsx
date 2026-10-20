import { useEffect, useState } from 'react'
import { Loader2, X, Plus, Minus, History } from 'lucide-react'
import { cappeApi } from '../api'
import type { CappeProduct, CappeInventoryAdjustment } from '../types'
import { variantName } from '../utils/variants'

const REASONS = ['restock', 'manual', 'damage', 'return', 'adjustment'] as const
const input = 'rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500'

// Manual stock adjustment + audit history for one product, its tracked
// combinations ("M / Red") and its options that keep their own stock. Calls
// POST /adjust and GET /inventory-log.
export default function StockAdjustModal({ siteId, product, onClose, onUpdated }: {
  siteId: string
  product: CappeProduct
  onClose: () => void
  onUpdated: (p: CappeProduct) => void
}) {
  // Everything that actually tracks stock (inventory !== null): combinations
  // first, then options with their own count. Keys are 'v:<id>' / 'o:<id>'.
  const targets = [
    ...(product.variants || []).filter((v) => v.inventory != null)
      .map((v) => ({ key: `v:${v.id}`, label: variantName(product, v.option_ids), inventory: v.inventory as number })),
    ...(product.option_groups || []).flatMap((g) =>
      (g.options || []).filter((o) => o.inventory != null).map((o) => ({ key: `o:${o.id}`, label: `${g.name}: ${o.name}`, inventory: o.inventory as number })),
    ),
  ]
  // '' = the product, else a target key. A product that doesn't track its own
  // count starts on its first tracked target: the picker shows that one, and
  // '' would send the adjustment to the product, which the server refuses.
  const [target, setTarget] = useState<string>(() => (product.inventory != null ? '' : targets[0]?.key ?? ''))
  const [delta, setDelta] = useState('1')
  const [sign, setSign] = useState<1 | -1>(1)
  const [reason, setReason] = useState<typeof REASONS[number]>('restock')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [log, setLog] = useState<CappeInventoryAdjustment[] | null>(null)
  const [logError, setLogError] = useState<string | null>(null)

  // A failed load used to show "No stock changes yet" — a false statement
  // about the stock record, not an error.
  function loadLog() {
    cappeApi.get<CappeInventoryAdjustment[]>(`/sites/${siteId}/products/${product.id}/inventory-log`)
      .then((rows) => { setLog(rows); setLogError(null) })
      .catch((e) => { setLog([]); setLogError(e instanceof Error ? e.message : 'Could not load the stock history') })
  }
  useEffect(loadLog, [siteId, product.id])
  function retryLog() {
    setLogError(null)
    setLog(null)
    loadLog()
  }

  async function submit() {
    const n = parseInt(delta, 10)
    if (!Number.isFinite(n) || n <= 0) { setError('Enter a quantity'); return }
    setBusy(true); setError(null)
    try {
      const updated = await cappeApi.post<CappeProduct>(`/sites/${siteId}/products/${product.id}/adjust`, {
        delta: sign * n,
        option_id: target.startsWith('o:') ? target.slice(2) : null,
        variant_id: target.startsWith('v:') ? target.slice(2) : null,
        reason,
        note: note.trim() || null,
      })
      onUpdated(updated)
      setNote(''); setDelta('1'); loadLog()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Adjustment failed')
    } finally {
      setBusy(false)
    }
  }

  const productTracks = product.inventory != null
  const optionName = (optionId: string) => {
    for (const g of product.option_groups || []) {
      const o = (g.options || []).find((x) => x.id === optionId)
      if (o) return `${g.name}: ${o.name}`
    }
    return 'a removed option'
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="max-h-[88vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-zinc-700 bg-zinc-900 p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-zinc-50">Adjust stock</h2>
            <p className="mt-0.5 text-sm text-zinc-400">{product.name}</p>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200"><X className="h-5 w-5" /></button>
        </div>

        {!productTracks && targets.length === 0 ? (
          <p className="rounded-lg border border-amber-700/40 bg-amber-500/[0.06] p-3 text-sm text-amber-200">
            This product isn't tracking stock. Set a stock number on the product (or a variant) first.
          </p>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Stock to adjust" className={input}>
                {productTracks && <option value="">Product ({product.inventory} in stock)</option>}
                {targets.map((t) => <option key={t.key} value={t.key}>{t.label} ({t.inventory})</option>)}
              </select>
              <div className="flex items-center gap-1">
                <button type="button" onClick={() => setSign(1)} className={`rounded-lg border px-2 py-1.5 ${sign === 1 ? 'border-emerald-500 bg-emerald-500/10 text-emerald-300' : 'border-zinc-700 text-zinc-400'}`}><Plus className="h-4 w-4" /></button>
                <button type="button" onClick={() => setSign(-1)} className={`rounded-lg border px-2 py-1.5 ${sign === -1 ? 'border-red-500 bg-red-500/10 text-red-300' : 'border-zinc-700 text-zinc-400'}`}><Minus className="h-4 w-4" /></button>
              </div>
              <input value={delta} onChange={(e) => setDelta(e.target.value)} type="number" min="1" className={`w-20 ${input}`} />
              <select value={reason} onChange={(e) => setReason(e.target.value as typeof REASONS[number])} aria-label="Reason" className={input}>
                {REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional)" className={`w-full ${input}`} />
            {error && <p className="text-sm text-red-400">{error}</p>}
            <button onClick={submit} disabled={busy} className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Apply
            </button>
          </div>
        )}

        <div className="mt-5 border-t border-zinc-800 pt-4">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-500"><History className="h-3.5 w-3.5" /> History</div>
          {logError ? (
            <p role="alert" className="text-xs text-red-400">
              Couldn’t load the stock history. {logError}{' '}
              <button onClick={retryLog} className="underline hover:text-red-300">Try again</button>
            </p>
          ) : log === null ? (
            <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />
          ) : log.length === 0 ? (
            <p className="text-xs text-zinc-500">No stock changes yet.</p>
          ) : (
            <ul className="max-h-56 space-y-1 overflow-y-auto text-xs">
              {log.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-2 rounded-md bg-zinc-950/60 px-2.5 py-1.5">
                  <span className="flex items-center gap-2">
                    <span className={`font-semibold ${a.delta >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{a.delta >= 0 ? `+${a.delta}` : a.delta}</span>
                    <span className="text-zinc-400">{a.reason}{a.variant_id ? ` · ${(product.variants || []).some((v) => v.id === a.variant_id)
                      ? variantName(product, (product.variants || []).find((v) => v.id === a.variant_id)!.option_ids)
                      : 'a removed combination'}` : ''}{a.option_id ? ` · ${optionName(a.option_id)}` : ''}{a.note ? ` · ${a.note}` : ''}</span>
                  </span>
                  <span className="text-zinc-500">{a.balance_after != null ? `→ ${a.balance_after}` : ''} · {new Date(a.created_at).toLocaleDateString()}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
