import { useEffect, useState } from 'react'
import { Loader2, Check, Truck } from 'lucide-react'
import { cappeApi } from '../api'
import { parseMoneyCents } from '../utils/money'
import type { CappeSite } from '../types'

// Flat per-order shipping for storefronts selling physical goods. Applied at
// checkout when the cart contains a physical line; free once the goods subtotal
// clears the optional threshold. Stripe collects the shipping address.
export default function ShippingSettingsCard({ siteId }: { siteId: string }) {
  const [flat, setFlat] = useState('') // dollars, as typed
  const [freeOver, setFreeOver] = useState('') // dollars; '' = no threshold
  const [label, setLabel] = useState('Shipping')
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    cappeApi.get<CappeSite>(`/sites/${siteId}`).then((s) => {
      setFlat(s.shipping_flat_cents ? (s.shipping_flat_cents / 100).toString() : '')
      setFreeOver(s.shipping_free_threshold_cents != null ? (s.shipping_free_threshold_cents / 100).toString() : '')
      setLabel(s.shipping_label || 'Shipping')
      setLoaded(true)
    }).catch(() => setLoaded(true))
  }, [siteId])

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
    setSaving(true)
    try {
      await cappeApi.put(`/sites/${siteId}`, {
        shipping_flat_cents: Math.max(0, flatCents),
        shipping_free_threshold_cents: freeCents === null ? null : Math.max(0, freeCents),
        shipping_label: label.trim() || 'Shipping',
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  if (!loaded) return null

  return (
    <div className="mb-5 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-zinc-200">
        <Truck className="h-4 w-4 text-lime-400" /> Shipping
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="text-xs text-zinc-400">
          Flat rate ($)
          <input
            value={flat}
            onChange={(e) => setFlat(e.target.value)}
            inputMode="decimal"
            placeholder="0"
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-lime-500"
          />
        </label>
        <label className="text-xs text-zinc-400">
          Free over ($)
          <input
            value={freeOver}
            onChange={(e) => setFreeOver(e.target.value)}
            inputMode="decimal"
            placeholder="No threshold"
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-lime-500"
          />
        </label>
        <label className="text-xs text-zinc-400">
          Label
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            maxLength={40}
            placeholder="Shipping"
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-lime-500"
          />
        </label>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="flex items-center gap-1.5 rounded-lg bg-zinc-100 px-3 py-1.5 text-sm font-semibold text-zinc-900 hover:bg-white disabled:opacity-60"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Save
        </button>
        {saved && <span className="text-xs text-lime-400">Saved</span>}
        {error && <span className="text-xs text-red-400">{error}</span>}
        <span className="ml-auto text-[11px] text-zinc-500">Applies once per order with a physical item. Address collected by Stripe.</span>
      </div>
    </div>
  )
}
