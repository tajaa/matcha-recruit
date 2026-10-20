import { useEffect, useState } from 'react'
import { Loader2, Check, Building2 } from 'lucide-react'
import { cappeApi } from '../api'
import type { CappeSite } from '../types'

// Who is selling: the legal name, business address and tax number printed on
// every receipt (an EU/UK VAT invoice needs all three), and whether Stripe's
// payment page asks buyers for a phone number (couriers often want one).

const field = 'mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-lime-500'

export default function BusinessIdentityCard({ siteId }: { siteId: string }) {
  const [legalName, setLegalName] = useState('')
  const [address, setAddress] = useState('')
  const [taxId, setTaxId] = useState('')
  const [taxLabel, setTaxLabel] = useState('Tax')
  const [phone, setPhone] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // A failed load must not fall through to the form: its blank boxes, saved,
  // would clear the store's real details.
  const [loadError, setLoadError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    cappeApi.get<CappeSite>(`/sites/${siteId}`).then((s) => {
      setLegalName(s.legal_name || '')
      setAddress(s.business_address || '')
      setTaxId(s.tax_id || '')
      setTaxLabel(s.tax_label || 'Tax')
      setPhone(!!s.collect_phone)
      setLoaded(true)
    }).catch((e) => setLoadError(e instanceof Error ? e.message : 'Could not load these settings'))
  }, [siteId, attempt])

  async function save() {
    setError(null); setSaved(false); setSaving(true)
    try {
      await cappeApi.put(`/sites/${siteId}`, {
        legal_name: legalName.trim() || null,
        business_address: address.trim() || null,
        tax_id: taxId.trim() || null,
        collect_phone: phone,
      })
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
        Couldn’t load your business details, so they can’t be edited right now. {loadError}
        <button onClick={() => { setLoadError(null); setAttempt((n) => n + 1) }} className="rounded-lg border border-red-500/40 px-2.5 py-1 text-xs font-medium hover:bg-red-500/10">Try again</button>
      </div>
    )
  }
  if (!loaded) return null

  return (
    <div className="mb-5 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-zinc-200">
        <Building2 className="h-4 w-4 text-lime-400" /> Business details on receipts
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="text-xs text-zinc-400">
          Legal business name
          <input value={legalName} onChange={(e) => setLegalName(e.target.value)} maxLength={200} placeholder="Lumen Candles Ltd" className={field} />
        </label>
        <label className="text-xs text-zinc-400">
          {taxLabel} number (optional)
          <input value={taxId} onChange={(e) => setTaxId(e.target.value)} maxLength={64} placeholder="GB123456789" className={field} />
        </label>
        <label className="text-xs text-zinc-400 sm:col-span-2">
          Business address
          <textarea value={address} onChange={(e) => setAddress(e.target.value)} maxLength={500} rows={3}
            placeholder={'12 Market Street\nBristol BS1 4DJ\nUnited Kingdom'} className={field} />
        </label>
      </div>
      <label className="mt-3 flex items-center gap-2 text-xs text-zinc-300">
        <input type="checkbox" checked={phone} onChange={(e) => setPhone(e.target.checked)} />
        Ask buyers for a phone number when they pay by card
      </label>
      <div className="mt-3 flex items-center gap-3">
        <button onClick={save} disabled={saving}
          className="flex items-center gap-1.5 rounded-lg bg-zinc-100 px-3 py-1.5 text-sm font-semibold text-zinc-900 hover:bg-white disabled:opacity-60">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Save
        </button>
        {saved && <span className="text-xs text-lime-400">Saved</span>}
        {error && <span role="alert" className="text-xs text-red-400">{error}</span>}
      </div>
    </div>
  )
}
