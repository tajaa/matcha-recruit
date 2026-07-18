import { useEffect, useState } from 'react'
import { Coins, Loader2, Plus } from 'lucide-react'
import { Card } from '../../../components/ui'
import { getTcor, upsertTcorInput, type TcorResult } from '../../../api/risk/tcor'

const money = (n: number | null | undefined) =>
  n == null ? '—' : n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(1)}M` : n >= 1_000 ? `$${Math.round(n / 1_000)}K` : `$${Math.round(n)}`

const LINES = ['wc', 'gl', 'auto', 'property', 'umbrella', 'cyber', 'epl', 'professional']

export default function Tcor() {
  const [data, setData] = useState<TcorResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({ line: 'wc', annual_premium: '', fees: '', risk_mitigation_spend: '', current_retention: '' })
  const [saving, setSaving] = useState(false)

  useEffect(() => { getTcor().then(setData).finally(() => setLoading(false)) }, [])

  async function save() {
    setSaving(true)
    try {
      const num = (s: string) => (s.trim() === '' ? null : Number(s))
      const res = await upsertTcorInput({
        line: form.line,
        annual_premium: num(form.annual_premium),
        fees: num(form.fees),
        risk_mitigation_spend: num(form.risk_mitigation_spend),
        current_retention: num(form.current_retention),
      })
      setData(res)
      setForm({ line: 'wc', annual_premium: '', fees: '', risk_mitigation_spend: '', current_retention: '' })
    } finally { setSaving(false) }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  if (!data) return <p className="text-sm text-zinc-500">Unable to load TCOR.</p>

  const opt = data.optimization
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          <Coins className="h-5 w-5 text-zinc-400" /> Total Cost of Risk
        </h1>
        <p className="text-sm text-zinc-500 mt-1 max-w-2xl">Premiums + modeled retained losses + fees + mitigation spend — the number a broker manages down. The retention optimizer prices candidate self-insured retentions against your simulated loss distribution.</p>
      </div>

      <Card className="p-5">
        <h2 className="text-sm font-medium text-zinc-300 mb-3">TCOR components — total {money(data.tcor.total)}</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {data.tcor.components.map((c) => (
            <div key={c.key} className="rounded-lg border border-zinc-800 p-3">
              <div className="text-xs text-zinc-500 capitalize">{c.key.replace(/_/g, ' ')}</div>
              <div className="text-lg font-semibold text-zinc-100">{money(c.amount)}</div>
              <div className="text-xs text-zinc-600">{c.share_pct}%</div>
            </div>
          ))}
        </div>
        {data.retained_losses_basis === 'none' && (
          <p className="text-xs text-amber-500/80 mt-3">Retained losses are 0 — run a risk assessment so the cost-of-risk model can feed the retention optimizer.</p>
        )}
      </Card>

      {opt && opt.candidates.length > 0 && (
        <Card className="p-5">
          <h2 className="text-sm font-medium text-zinc-300 mb-1">Aggregate retention optimizer</h2>
          <p className="text-xs text-zinc-600 mb-3">{opt.basis}</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
                <th className="py-2 pr-4">Retention</th><th className="pr-4">Expected retained</th><th className="pr-4">Volatility</th><th className="pr-4">Premium</th><th className="pr-4">Expected total</th><th>Risk-adj cost</th>
              </tr></thead>
              <tbody>
                {opt.candidates.map((r) => {
                  const rec = r.retention === opt.recommended_retention
                  return (
                    <tr key={r.retention} className={`border-b border-zinc-900 ${rec ? 'bg-emerald-500/10' : ''}`}>
                      <td className="py-2 pr-4 text-zinc-200">{money(r.retention)}{rec && <span className="ml-2 text-xs text-emerald-400">recommended</span>}</td>
                      <td className="pr-4 text-zinc-400">{money(r.expected_retained)}</td>
                      <td className="pr-4 text-zinc-400">{money(r.volatility)}</td>
                      <td className="pr-4 text-zinc-400">{money(r.premium)}</td>
                      <td className="pr-4 text-zinc-200">{money(r.expected_total_cost)}</td>
                      <td className="text-zinc-200">{money(r.risk_adjusted_cost)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card className="p-5">
        <h2 className="text-sm font-medium text-zinc-300 mb-3 flex items-center gap-2"><Plus className="h-4 w-4" /> Add / update line inputs</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <label className="text-xs text-zinc-500">Line
            <select value={form.line} onChange={(e) => setForm({ ...form, line: e.target.value })} className="mt-1 w-full bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1.5 text-sm text-zinc-200 capitalize">
              {LINES.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </label>
          {(['annual_premium', 'fees', 'risk_mitigation_spend', 'current_retention'] as const).map((k) => (
            <label key={k} className="text-xs text-zinc-500 capitalize">{k.replace(/_/g, ' ')}
              <input type="number" value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} className="mt-1 w-full bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1.5 text-sm text-zinc-200" />
            </label>
          ))}
        </div>
        <button onClick={save} disabled={saving} className="mt-3 inline-flex items-center gap-1.5 text-sm text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-2 font-medium disabled:opacity-50">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Save
        </button>
      </Card>
    </div>
  )
}
