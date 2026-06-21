import { useState, useEffect, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Globe, Plus, Loader2, AlertCircle } from 'lucide-react'
import { Card } from '../../components/ui'
import { HelpHint } from '../../components/broker/HelpHint'
import { fetchExternalClients, createExternalClient } from '../../api/broker'
import type { ExternalClientRow } from '../../types/broker'

const WC_TONE: Record<string, string> = {
  critical: 'text-red-400', at_risk: 'text-orange-400', fair: 'text-amber-400',
  good: 'text-emerald-400', unknown: 'text-zinc-600',
}
const EPL_TONE: Record<string, string> = {
  strong: 'text-emerald-400', adequate: 'text-amber-400', developing: 'text-orange-400', exposed: 'text-red-400',
}
const inputCls = 'w-full bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500'

export default function BrokerExternalClients() {
  const [clients, setClients] = useState<ExternalClientRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', industry: '', headcount: '', primary_state: '', note: '' })
  const [saving, setSaving] = useState(false)
  const [formErr, setFormErr] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(false)
    fetchExternalClients().then((r) => setClients(r.clients)).catch(() => setError(true)).finally(() => setLoading(false))
  }
  useEffect(load, [])

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!form.name.trim()) { setFormErr('Name is required.'); return }
    setSaving(true)
    setFormErr(null)
    try {
      await createExternalClient({
        name: form.name.trim(),
        industry: form.industry || null,
        headcount: form.headcount ? parseInt(form.headcount, 10) : null,
        primary_state: form.primary_state || null,
        note: form.note || null,
      })
      setForm({ name: '', industry: '', headcount: '', primary_state: '', note: '' })
      setShowForm(false)
      load()
    } catch { setFormErr('Could not create. Try again.') }
    finally { setSaving(false) }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
            <Globe className="h-5 w-5 text-zinc-400" /> External Book
            <HelpHint text="Your off-platform book — clients who aren't on Matcha. Add one, key in their carrier loss run + a short EPL questionnaire, and the same WC + EPL engine scores them. Lets you advise prospects and renewals across your whole book, not just onboarded clients." />
          </h1>
          <p className="text-sm text-zinc-500 mt-1">Clients not on Matcha — key in their loss run + EPL questionnaire to score them.</p>
        </div>
        <button onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-1.5 text-sm text-zinc-200 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors">
          <Plus className="h-4 w-4" /> Add client
        </button>
      </div>

      {showForm && (
        <Card className="p-4">
          <form onSubmit={submit} className="grid grid-cols-1 sm:grid-cols-5 gap-2 items-end">
            <div className="sm:col-span-2">
              <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Client name *</label>
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={inputCls} placeholder="Acme Trucking" />
            </div>
            <div>
              <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Industry</label>
              <input value={form.industry} onChange={(e) => setForm({ ...form, industry: e.target.value })} className={inputCls} placeholder="construction" />
            </div>
            <div>
              <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Headcount</label>
              <input type="number" value={form.headcount} onChange={(e) => setForm({ ...form, headcount: e.target.value })} className={inputCls} placeholder="40" />
            </div>
            <div>
              <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">State</label>
              <input value={form.primary_state} onChange={(e) => setForm({ ...form, primary_state: e.target.value })} className={inputCls} placeholder="CA" maxLength={2} />
            </div>
            <div className="sm:col-span-4">
              <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Note</label>
              <input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} className={inputCls} placeholder="optional" />
            </div>
            <div>
              <button type="submit" disabled={saving} className="w-full bg-zinc-100 text-zinc-900 text-sm font-medium rounded-lg px-3 py-1.5 hover:bg-white disabled:opacity-50 transition-colors">
                {saving ? 'Saving…' : 'Create'}
              </button>
            </div>
            {formErr && <p className="sm:col-span-5 text-[11px] text-red-400">{formErr}</p>}
          </form>
        </Card>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-48"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center h-48 text-zinc-500">
          <AlertCircle className="h-8 w-8 mb-2" /><p className="text-sm">Unable to load external clients.</p>
        </div>
      ) : clients.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-sm text-zinc-400">No external clients yet.</p>
          <p className="text-xs text-zinc-600 mt-1">Add a prospect or off-platform book client to score their WC + EPL risk.</p>
        </Card>
      ) : (
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-800/60 bg-zinc-900/40">
                <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Client</th>
                <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Industry</th>
                <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">State</th>
                <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">
                  <span className="inline-flex items-center gap-1 justify-end">WC <HelpHint align="right" text="Workers' Comp injury rate (TRIR) vs the client's industry, colored worst→best. Lower is better. Dash = no loss run entered yet." /></span>
                </th>
                <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">
                  <span className="inline-flex items-center gap-1 justify-end">EMR <HelpHint align="right" text="Experience modification rate — the multiplier carriers apply to WC premium. Above 1.00 = surcharge (debit); below = credit." /></span>
                </th>
                <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">
                  <span className="inline-flex items-center gap-1 justify-end">EPL <HelpHint align="right" text="Employment-practices-liability readiness, 0–100 with a band (Strong→Exposed). How insurable the client looks + what to fix before renewal." /></span>
                </th>
              </tr>
            </thead>
            <tbody>
              {clients.map((c) => (
                <tr key={c.id} className="border-b border-zinc-800/30 last:border-0 hover:bg-zinc-900/30">
                  <td className="px-4 py-3">
                    <Link to={`/broker/external/${c.id}`} className="text-zinc-100 font-medium hover:text-emerald-400 transition-colors">{c.name}</Link>
                  </td>
                  <td className="px-4 py-3 text-zinc-400 text-xs">{c.industry ?? '—'}</td>
                  <td className="px-4 py-3 text-zinc-400">{c.primary_state ?? '—'}</td>
                  <td className={`px-4 py-3 text-right font-mono ${WC_TONE[c.wc_severity_band] ?? 'text-zinc-600'}`}>
                    {c.wc_trir != null ? c.wc_trir.toFixed(1) : '—'}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-zinc-300">{c.wc_current_emr != null ? c.wc_current_emr.toFixed(2) : '—'}</td>
                  <td className={`px-4 py-3 text-right font-mono ${EPL_TONE[c.epl_band] ?? 'text-zinc-600'}`}>
                    {c.epl_score} <span className="text-[10px] uppercase">{c.epl_band}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
