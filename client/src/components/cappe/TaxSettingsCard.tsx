import { useEffect, useState } from 'react'
import { Loader2, Check, Percent } from 'lucide-react'
import { cappeApi } from '../../api/cappeClient'
import type { CappeSite } from '../../types/cappe'

// Compact tax + receipt-numbering settings for the storefront. Rate is stored in
// basis points (875 = 8.75%); applied to physical lines at checkout and added to
// the Stripe charge so it matches the receipt. Prefix seeds receipt numbers
// (e.g. LUM → LUM-00042).
export default function TaxSettingsCard({ siteId }: { siteId: string }) {
  const [rate, setRate] = useState('') // percent, as typed
  const [label, setLabel] = useState('Tax')
  const [prefix, setPrefix] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    cappeApi.get<CappeSite>(`/sites/${siteId}`).then((s) => {
      setRate(s.tax_rate_bps ? (s.tax_rate_bps / 100).toString() : '')
      setLabel(s.tax_label || 'Tax')
      setPrefix(s.receipt_prefix || '')
      setLoaded(true)
    }).catch(() => setLoaded(true))
  }, [siteId])

  async function save() {
    setSaving(true); setError(null); setSaved(false)
    const pct = parseFloat(rate)
    const bps = Number.isFinite(pct) ? Math.max(0, Math.min(10000, Math.round(pct * 100))) : 0
    try {
      await cappeApi.put(`/sites/${siteId}`, {
        tax_rate_bps: bps,
        tax_label: label.trim() || 'Tax',
        receipt_prefix: prefix.trim().toUpperCase() || null,
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
        <Percent className="h-4 w-4 text-lime-400" /> Tax &amp; receipts
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="text-xs text-zinc-400">
          Tax rate (%)
          <input
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            inputMode="decimal"
            placeholder="0"
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-lime-500"
          />
        </label>
        <label className="text-xs text-zinc-400">
          Tax label
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            maxLength={40}
            placeholder="Sales tax"
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-lime-500"
          />
        </label>
        <label className="text-xs text-zinc-400">
          Receipt prefix
          <input
            value={prefix}
            onChange={(e) => setPrefix(e.target.value)}
            maxLength={12}
            placeholder="INV"
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm uppercase text-zinc-100 outline-none focus:border-lime-500"
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
        <span className="ml-auto text-[11px] text-zinc-500">Tax applies to physical products at checkout.</span>
      </div>
    </div>
  )
}
