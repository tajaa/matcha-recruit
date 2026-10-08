import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, Plus, Tag, Trash2, Pencil } from 'lucide-react'
import { cappeApi } from '../api'
import { centsToMoney } from './SurfaceShell'
import { EMPTY, toBody, toForm, type Form } from '../utils/promoCodes'
import { BILLING_PATH } from '../pages/CappeBilling/paths'
import type { CappePromoCode, CappePromoCodes } from '../types'

// Codes buyers type in the bag. A code takes its discount off the items that
// aren't already on sale, before tax and shipping; uses are counted at order
// time and given back when an order is cancelled or refunded in full.

const field = 'mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-lime-500'

function describe(c: CappePromoCode, currency: string) {
  const off = c.kind === 'percent' ? `${c.percent_off}% off` : `${centsToMoney(c.amount_off_cents ?? 0, currency)} off`
  const bits = [off]
  if (c.min_subtotal_cents) bits.push(`over ${centsToMoney(c.min_subtotal_cents, currency)}`)
  if (c.ends_on) bits.push(`until ${new Date(`${c.ends_on}T00:00:00`).toLocaleDateString()}`)
  if (c.once_per_customer) bits.push('once per customer')
  return bits.join(' · ')
}

// `currency` is the store's live currency from the page, once known: it can
// change in the shipping card after this card loaded.
export default function PromoCodesCard({ siteId, currency }: { siteId: string; currency?: string | null }) {
  const [data, setData] = useState<CappePromoCodes | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [form, setForm] = useState<Form | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    cappeApi.get<CappePromoCodes>(`/sites/${siteId}/promo-codes`)
      .then((d) => { setData(d); setLoadError(null) })
      .catch((e) => setLoadError(e instanceof Error ? e.message : 'Could not load your promo codes'))
  }, [siteId, attempt])

  async function save() {
    if (!form) return
    const body = toBody(form)
    if (typeof body === 'string') { setError(body); return }
    setSaving(true); setError(null)
    try {
      const saved = editingId
        ? await cappeApi.put<CappePromoCode>(`/sites/${siteId}/promo-codes/${editingId}`, body)
        : await cappeApi.post<CappePromoCode>(`/sites/${siteId}/promo-codes`, body)
      setData((d) => d && {
        ...d,
        codes: editingId ? d.codes.map((c) => (c.id === saved.id ? saved : c)) : [saved, ...d.codes],
      })
      setForm(null); setEditingId(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save this code')
    } finally {
      setSaving(false)
    }
  }

  async function remove(c: CappePromoCode) {
    if (!window.confirm(`Delete ${c.code}? Orders that used it keep their discount.`)) return
    setError(null)
    try {
      await cappeApi.delete(`/sites/${siteId}/promo-codes/${c.id}`)
      setData((d) => d && { ...d, codes: d.codes.filter((x) => x.id !== c.id) })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete this code')
    }
  }

  if (loadError) {
    return (
      <div role="alert" className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">
        Couldn’t load your promo codes. {loadError}
        <button onClick={() => { setLoadError(null); setAttempt((n) => n + 1) }} className="rounded-lg border border-red-500/40 px-2.5 py-1 text-xs font-medium hover:bg-red-500/10">Try again</button>
      </div>
    )
  }
  if (!data) return null
  const cur = currency || data.currency

  return (
    <div className="mb-5 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-zinc-200">
        <Tag className="h-4 w-4 text-lime-400" /> Promo codes
        {data.enabled && !form && (
          <button onClick={() => { setForm(EMPTY); setEditingId(null); setError(null) }}
            className="ml-auto flex items-center gap-1 text-xs font-medium text-lime-400 hover:text-lime-300">
            <Plus className="h-3.5 w-3.5" /> New code
          </button>
        )}
      </div>
      {!data.enabled && (
        <p className="text-xs text-zinc-400">
          Promo codes come with paid plans. <Link to={BILLING_PATH} className="text-lime-400 hover:underline">See plans</Link>
          {data.codes.length > 0 && ' — your existing codes can’t be used until you upgrade.'}
        </p>
      )}
      {data.codes.length === 0 && data.enabled && !form && (
        <p className="text-xs text-zinc-400">No codes yet. Buyers type a code in their bag; it comes off items that aren’t already on sale.</p>
      )}
      {data.codes.length > 0 && (
        <ul className="divide-y divide-zinc-800">
          {data.codes.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
              <span className="font-mono font-semibold text-zinc-100">{c.code}</span>
              {!c.active && <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] uppercase text-zinc-400">Off</span>}
              <span className="text-xs text-zinc-400">{describe(c, cur)}</span>
              <span className="ml-auto text-xs text-zinc-500">
                Used {c.redemption_count}{c.max_redemptions ? ` of ${c.max_redemptions}` : ''}
              </span>
              {data.enabled && (
                <button onClick={() => { setForm(toForm(c)); setEditingId(c.id); setError(null) }} aria-label={`Edit ${c.code}`}
                  className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"><Pencil className="h-3.5 w-3.5" /></button>
              )}
              <button onClick={() => remove(c)} aria-label={`Delete ${c.code}`}
                className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-red-300"><Trash2 className="h-3.5 w-3.5" /></button>
            </li>
          ))}
        </ul>
      )}
      {form && (
        <div className="mt-3 space-y-3 rounded-lg border border-zinc-800 bg-zinc-950/40 p-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="text-xs text-zinc-400">Code
              <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} maxLength={40} placeholder="SUMMER10" className={`${field} font-mono`} />
            </label>
            <label className="text-xs text-zinc-400">Type
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as Form['kind'] })} className={field}>
                <option value="percent">Percent off</option>
                <option value="fixed">Amount off ({cur})</option>
              </select>
            </label>
            <label className="text-xs text-zinc-400">{form.kind === 'percent' ? 'Percent' : `Amount (${cur})`}
              <input value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} inputMode="decimal" placeholder={form.kind === 'percent' ? '10' : '5'} className={field} />
            </label>
            <label className="text-xs text-zinc-400">Minimum spend ({cur})
              <input value={form.minimum} onChange={(e) => setForm({ ...form, minimum: e.target.value })} inputMode="decimal" placeholder="None" className={field} />
            </label>
            <label className="text-xs text-zinc-400">Starts
              <input type="date" value={form.starts} onChange={(e) => setForm({ ...form, starts: e.target.value })} className={field} />
            </label>
            <label className="text-xs text-zinc-400">Ends
              <input type="date" value={form.ends} onChange={(e) => setForm({ ...form, ends: e.target.value })} className={field} />
            </label>
            <label className="text-xs text-zinc-400">Total uses
              <input value={form.cap} onChange={(e) => setForm({ ...form, cap: e.target.value })} inputMode="numeric" placeholder="Unlimited" className={field} />
            </label>
            <label className="flex items-end gap-2 pb-2 text-xs text-zinc-300">
              <input type="checkbox" checked={form.once} onChange={(e) => setForm({ ...form, once: e.target.checked })} /> Once per customer
            </label>
            <label className="flex items-end gap-2 pb-2 text-xs text-zinc-300">
              <input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /> Active
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button onClick={save} disabled={saving}
              className="flex items-center gap-1.5 rounded-lg bg-zinc-100 px-3 py-1.5 text-sm font-semibold text-zinc-900 hover:bg-white disabled:opacity-60">
              {saving && <Loader2 className="h-4 w-4 animate-spin" />} {editingId ? 'Save code' : 'Create code'}
            </button>
            <button onClick={() => { setForm(null); setEditingId(null); setError(null) }} className="text-xs text-zinc-400 hover:text-zinc-200">Cancel</button>
          </div>
        </div>
      )}
      {error && <p role="alert" className="mt-2 text-xs text-red-400">{error}</p>}
    </div>
  )
}
