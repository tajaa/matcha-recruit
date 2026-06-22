import { useEffect, useState, type FormEvent } from 'react'
import { ShieldCheck, Bot, Fingerprint, Plus, Trash2, Loader2, AlertTriangle, Check, Scale, Sparkles } from 'lucide-react'
import { Card } from '../../components/ui'
import {
  fetchAiAudits, createAiAudit, updateAiAudit, deleteAiAudit,
  fetchBiometricPoints, createBiometricPoint, updateBiometricPoint, deleteBiometricPoint,
  fetchPayTransparency, setPayTransparency,
  fetchPayEquityReviews, createPayEquityReview, deletePayEquityReview, analyzePayEquity, fetchPayEquityAnalysis,
  suggestAiAudits, suggestBiometricPoints,
} from '../../api/workforceCompliance'
import { AiSuggest } from '../../components/AiSuggest'
import type {
  AiAudit, BiometricPoint, PayTransparencyRow, PayTransparencyStatus, CollectionType, PayEquityReview,
  PayEquityAnalysisResult, PayEquityRole, PayEquityPriorityAction,
} from '../../types/workforceCompliance'

const today = () => new Date().toISOString().slice(0, 10)
const inputCls = 'w-full bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500'
const PT_TONE: Record<string, string> = { compliant: 'text-emerald-400', action_needed: 'text-red-400', na: 'text-zinc-500' }
const COLLECTION_TYPES: CollectionType[] = ['fingerprint', 'face', 'iris', 'voice', 'hand_geometry', 'other']
const PE_TONE: Record<string, string> = { flag: 'text-red-400', watch: 'text-amber-400', ok: 'text-emerald-400' }
const PE_LABEL: Record<string, string> = { flag: 'Flag', watch: 'Watch', ok: 'OK' }
const PE_BAR: Record<string, string> = { flag: 'bg-red-400', watch: 'bg-amber-400', ok: 'bg-emerald-400' }
const PE_POSTURE: Record<string, { tone: string; dot: string }> = {
  equitable: { tone: 'text-emerald-400', dot: 'bg-emerald-400' },
  watch: { tone: 'text-amber-400', dot: 'bg-amber-400' },
  action: { tone: 'text-red-400', dot: 'bg-red-400' },
  insufficient: { tone: 'text-zinc-500', dot: 'bg-zinc-600' },
}
function fmtUsd(n: number | null): string {
  if (n == null) return '—'
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`
  if (Math.abs(n) >= 1_000) return `$${Math.round(n / 1000)}K`
  return `$${Math.round(n).toLocaleString()}`
}

export default function WorkforceCompliance() {
  const [audits, setAudits] = useState<AiAudit[]>([])
  const [points, setPoints] = useState<BiometricPoint[]>([])
  const [pt, setPt] = useState<PayTransparencyRow[]>([])
  const [payEquity, setPayEquity] = useState<PayEquityReview[]>([])
  const [loading, setLoading] = useState(true)

  function load() {
    setLoading(true)
    Promise.allSettled([
      fetchAiAudits().then(setAudits),
      fetchBiometricPoints().then(setPoints),
      fetchPayTransparency().then(setPt),
      fetchPayEquityReviews().then(setPayEquity),
    ]).finally(() => setLoading(false))
  }
  useEffect(load, [])

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  }

  const ptAction = pt.filter((r) => r.required && r.status !== 'compliant').length
  const overdue = audits.filter((a) => a.is_overdue).length
  const missingConsent = points.filter((p) => p.is_active && !p.consent_obtained).length
  const peOverdue = payEquity.filter((r) => r.is_overdue).length
  const peNone = payEquity.length === 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-zinc-400" /> Workforce Compliance
        </h1>
        <p className="text-sm text-zinc-500 mt-1">Employment-practices risk controls — pay transparency, AI hiring-tool audits, biometric consent, and pay-equity studies. Tracked for your own compliance; also strengthens your EPL insurance profile.</p>
      </div>

      {/* Summary strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
        {[
          { label: 'Pay-Transparency · Action', value: ptAction, warn: ptAction > 0 },
          { label: 'AI Audits · Overdue', value: overdue, warn: overdue > 0 },
          { label: 'Biometric · Missing Consent', value: missingConsent, warn: missingConsent > 0 },
          { label: 'Pay-Equity · Overdue', value: peNone ? '—' : peOverdue, warn: peOverdue > 0 || peNone },
        ].map((c) => (
          <div key={c.label} className="bg-zinc-900 px-4 py-4">
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{c.label}</div>
            <div className={`text-2xl font-light font-mono mt-1.5 ${c.warn ? 'text-red-400' : 'text-emerald-400'}`}>{c.value}</div>
          </div>
        ))}
      </div>

      <PayTransparencySection rows={pt} onChange={setPt} />
      <AiAuditSection audits={audits} reload={load} />
      <BiometricSection points={points} reload={load} />
      <PayEquitySection reviews={payEquity} reload={load} />
    </div>
  )
}

/* ── Pay transparency ── */
function PayTransparencySection({ rows, onChange }: { rows: PayTransparencyRow[]; onChange: (r: PayTransparencyRow[]) => void }) {
  const [saving, setSaving] = useState<string | null>(null)
  async function set(state: string, status: PayTransparencyStatus, postings: boolean) {
    setSaving(state)
    try { onChange(await setPayTransparency(state, { status, postings_include_ranges: postings })) }
    finally { setSaving(null) }
  }
  const required = rows.filter((r) => r.required)
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-1"><ShieldCheck className="h-4 w-4 text-zinc-500" /><h3 className="text-sm font-medium text-zinc-200 tracking-wide">Pay transparency</h3></div>
      <p className="text-[11px] text-zinc-500 mb-3">States in your footprint that require salary ranges in job postings. Mark each compliant once your postings include ranges.</p>
      {required.length === 0 ? (
        <p className="text-sm text-zinc-500">No pay-transparency states in your locations.</p>
      ) : (
        <div className="space-y-1">
          {required.map((r) => (
            <div key={r.state} className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
              <span className="text-sm font-medium text-zinc-200 w-8">{r.state}</span>
              <span className={`text-[11px] font-semibold uppercase flex-1 ${PT_TONE[r.status]}`}>{r.status.replace('_', ' ')}</span>
              {saving === r.state && <Loader2 className="h-3.5 w-3.5 text-zinc-500 animate-spin" />}
              <label className="inline-flex items-center gap-1.5 text-xs text-zinc-400">
                <input type="checkbox" checked={r.postings_include_ranges} disabled={saving === r.state}
                  onChange={(e) => set(r.state, e.target.checked ? 'compliant' : 'action_needed', e.target.checked)}
                  className="h-3.5 w-3.5 rounded border-zinc-700 bg-zinc-900" />
                postings include ranges
              </label>
              <select value={r.status} disabled={saving === r.state}
                onChange={(e) => set(r.state, e.target.value as PayTransparencyStatus, r.postings_include_ranges)}
                className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500">
                <option value="action_needed">Action needed</option>
                <option value="compliant">Compliant</option>
                <option value="na">N/A</option>
              </select>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

/* ── AI hiring-tool audits ── */
function AiAuditSection({ audits, reload }: { audits: AiAudit[]; reload: () => void }) {
  const [show, setShow] = useState(false)
  const [form, setForm] = useState({ tool_name: '', vendor: '', last_audit_date: '', cadence_days: '365' })
  const [busy, setBusy] = useState(false)
  async function add(e: FormEvent) {
    e.preventDefault()
    if (!form.tool_name.trim()) return
    setBusy(true)
    try {
      await createAiAudit({ tool_name: form.tool_name.trim(), vendor: form.vendor || null, last_audit_date: form.last_audit_date || null, cadence_days: parseInt(form.cadence_days, 10) || 365 })
      setForm({ tool_name: '', vendor: '', last_audit_date: '', cadence_days: '365' }); setShow(false); reload()
    } finally { setBusy(false) }
  }
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2"><Bot className="h-4 w-4 text-zinc-500" /><h3 className="text-sm font-medium text-zinc-200 tracking-wide">AI hiring-tool audits</h3></div>
        <div className="flex items-center gap-2">
          <AiSuggest
            fetchSuggestions={suggestAiAudits}
            itemLabel={(s) => `${s.tool_name}${s.vendor ? ` · ${s.vendor}` : ''}${s.purpose ? ` — ${s.purpose}` : ''}`}
            createItem={(s) => createAiAudit({ tool_name: s.tool_name, vendor: s.vendor, purpose: s.purpose })}
            onDone={reload}
          />
          <button onClick={() => setShow((v) => !v)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700 hover:border-zinc-500"><Plus className="h-3.5 w-3.5" /> Add tool</button>
        </div>
      </div>
      <p className="text-[11px] text-zinc-500 mb-3">Register every automated hiring tool + its last bias-audit date (NYC LL144 / IL / CO require regular audits).</p>
      {show && (
        <form onSubmit={add} className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4 p-3 rounded-xl bg-zinc-900/60 border border-zinc-800">
          <input className={inputCls} placeholder="Tool name" value={form.tool_name} onChange={(e) => setForm({ ...form, tool_name: e.target.value })} />
          <input className={inputCls} placeholder="Vendor" value={form.vendor} onChange={(e) => setForm({ ...form, vendor: e.target.value })} />
          <div><label className="block text-[10px] text-zinc-500 uppercase mb-1">Last audit</label><input type="date" className={inputCls} value={form.last_audit_date} onChange={(e) => setForm({ ...form, last_audit_date: e.target.value })} /></div>
          <button type="submit" disabled={busy} className="bg-zinc-100 text-zinc-900 text-sm font-medium rounded-lg px-3 py-1.5 hover:bg-white disabled:opacity-50 self-end">{busy ? '…' : 'Add'}</button>
        </form>
      )}
      {audits.length === 0 ? <p className="text-sm text-zinc-500">No AI hiring tools registered.</p> : (
        <div className="space-y-1">
          {audits.map((a) => (
            <div key={a.id} className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
              <div className="flex-1 min-w-0">
                <span className="text-sm text-zinc-200">{a.tool_name}</span>{a.vendor && <span className="text-[11px] text-zinc-600 ml-2">{a.vendor}</span>}
                <div className="text-[11px] text-zinc-500">last audit {a.last_audit_date ?? 'never'} · due {a.next_due_date ?? '—'}</div>
              </div>
              {a.is_overdue && <span className="inline-flex items-center gap-1 text-[11px] text-red-400"><AlertTriangle className="h-3 w-3" /> overdue</span>}
              <button onClick={() => updateAiAudit(a.id, { last_audit_date: today() }).then(reload)} className="text-xs text-zinc-300 hover:text-emerald-400 px-2 py-1 rounded-lg border border-zinc-700">Mark audited</button>
              <button onClick={() => deleteAiAudit(a.id).then(reload)} className="text-zinc-600 hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

/* ── Biometric consent ── */
function BiometricSection({ points, reload }: { points: BiometricPoint[]; reload: () => void }) {
  const [show, setShow] = useState(false)
  const [form, setForm] = useState<{ collection_type: CollectionType; purpose: string; consent_obtained: boolean }>({ collection_type: 'fingerprint', purpose: '', consent_obtained: false })
  const [busy, setBusy] = useState(false)
  async function add(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await createBiometricPoint({ collection_type: form.collection_type, purpose: form.purpose || null, consent_obtained: form.consent_obtained, consent_obtained_date: form.consent_obtained ? today() : null })
      setForm({ collection_type: 'fingerprint', purpose: '', consent_obtained: false }); setShow(false); reload()
    } finally { setBusy(false) }
  }
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2"><Fingerprint className="h-4 w-4 text-zinc-500" /><h3 className="text-sm font-medium text-zinc-200 tracking-wide">Biometric consent (BIPA)</h3></div>
        <div className="flex items-center gap-2">
          <AiSuggest
            fetchSuggestions={suggestBiometricPoints}
            itemLabel={(s) => `${s.collection_type.replace('_', ' ')}${s.purpose ? ` — ${s.purpose}` : ''}`}
            createItem={(s) => createBiometricPoint({ collection_type: s.collection_type, purpose: s.purpose })}
            onDone={reload}
          />
          <button onClick={() => setShow((v) => !v)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700 hover:border-zinc-500"><Plus className="h-3.5 w-3.5" /> Add</button>
        </div>
      </div>
      <p className="text-[11px] text-zinc-500 mb-3">Every biometric collection point (time clocks, access control) + whether written consent is on file. BIPA carries $1–5k statutory damages per violation.</p>
      {show && (
        <form onSubmit={add} className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4 p-3 rounded-xl bg-zinc-900/60 border border-zinc-800 items-end">
          <div><label className="block text-[10px] text-zinc-500 uppercase mb-1">Type</label>
            <select className={inputCls} value={form.collection_type} onChange={(e) => setForm({ ...form, collection_type: e.target.value as CollectionType })}>
              {COLLECTION_TYPES.map((t) => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
            </select></div>
          <input className={inputCls} placeholder="Purpose (e.g. time clock)" value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} />
          <label className="inline-flex items-center gap-1.5 text-xs text-zinc-400"><input type="checkbox" checked={form.consent_obtained} onChange={(e) => setForm({ ...form, consent_obtained: e.target.checked })} className="h-3.5 w-3.5 rounded border-zinc-700 bg-zinc-900" /> consent on file</label>
          <button type="submit" disabled={busy} className="bg-zinc-100 text-zinc-900 text-sm font-medium rounded-lg px-3 py-1.5 hover:bg-white disabled:opacity-50">{busy ? '…' : 'Add'}</button>
        </form>
      )}
      {points.length === 0 ? <p className="text-sm text-zinc-500">No biometric collection points.</p> : (
        <div className="space-y-1">
          {points.map((p) => (
            <div key={p.id} className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
              <span className="text-sm text-zinc-200 capitalize flex-1">{p.collection_type.replace('_', ' ')}{p.purpose && <span className="text-[11px] text-zinc-600 ml-2">{p.purpose}</span>}</span>
              {p.consent_obtained ? <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400"><Check className="h-3 w-3" /> consent</span>
                : <button onClick={() => updateBiometricPoint(p.id, { consent_obtained: true, consent_obtained_date: today() }).then(reload)} className="text-[11px] text-red-400 hover:text-emerald-400 px-2 py-1 rounded-lg border border-zinc-700">mark consent</button>}
              <button onClick={() => deleteBiometricPoint(p.id).then(reload)} className="text-zinc-600 hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

/* min–max range bar with a median tick, coloured by severity */
function SpreadBar({ r }: { r: PayEquityRole }) {
  const span = Math.max(1, r.max - r.min)
  const medPct = Math.min(100, Math.max(0, ((r.median - r.min) / span) * 100))
  return (
    <div className="relative h-1.5 rounded-full bg-zinc-800" title={`${fmtUsd(r.min)} – ${fmtUsd(r.max)} (median ${fmtUsd(r.median)})${r.range_ratio ? ` · ${r.range_ratio}× high-to-low` : ''}`}>
      <div className={`absolute inset-0 rounded-full opacity-25 ${PE_BAR[r.severity]}`} />
      <div className="absolute top-[-2px] bottom-[-2px] w-0.5 bg-zinc-100" style={{ left: `${medPct}%` }} />
    </div>
  )
}

/* deep within-role dispersion report (rollups + per-role table) */
function PayEquityReport({ a }: { a: PayEquityAnalysisResult }) {
  if (!a.analyzed_roles) {
    return <p className="text-[11px] text-zinc-500 mb-3">Not enough comp data to analyze — need ≥2 employees sharing a job title with pay on file.</p>
  }
  const stats: { label: string; value: string | number; warn?: boolean }[] = [
    { label: 'Employees', value: a.employee_count },
    { label: 'Roles analyzed', value: a.analyzed_roles },
    { label: 'Median role spread', value: `${a.median_spread_pct}%` },
    { label: `Below ${a.band_floor_pct}% band`, value: a.employees_below_band, warn: a.employees_below_band > 0 },
    { label: 'Est. remediation', value: fmtUsd(a.remediation_estimate), warn: a.remediation_estimate > 0 },
    { label: 'Pay in flagged roles', value: `${a.flagged_payroll_pct}%`, warn: a.flagged_payroll_pct > 0 },
  ]
  const posture = PE_POSTURE[a.posture.band] ?? PE_POSTURE.insufficient
  return (
    <div className="mb-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Pay-equity posture</span>
        <span className={`inline-flex items-center gap-1.5 text-xs font-semibold ${posture.tone}`}>
          <span className={`h-2 w-2 rounded-full ${posture.dot}`} /> {a.posture.label}
        </span>
      </div>
      <div className="grid grid-cols-3 md:grid-cols-6 gap-px bg-white/10 border border-white/10 rounded-xl overflow-hidden mb-3">
        {stats.map((s) => (
          <div key={s.label} className="bg-zinc-900 px-3 py-2.5">
            <div className="text-[8px] text-zinc-600 uppercase tracking-widest font-bold leading-tight">{s.label}</div>
            <div className={`text-lg font-light font-mono mt-1 ${s.warn ? 'text-amber-400' : 'text-zinc-200'}`}>{s.value}</div>
          </div>
        ))}
      </div>
      {a.priority_actions.length > 0 && (
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/[0.04] px-3 py-2.5 mb-3">
          <div className="text-[9px] text-amber-400/80 uppercase tracking-widest font-bold mb-1.5">Priority fixes</div>
          <ol className="space-y-1">
            {a.priority_actions.map((p: PayEquityPriorityAction, i) => (
              <li key={p.title} className="flex items-start gap-2 text-[12px] text-zinc-300">
                <span className="text-zinc-600 font-mono mt-px">{i + 1}.</span>
                <span className={`h-2 w-2 rounded-full mt-1.5 flex-shrink-0 ${PE_BAR[p.severity]}`} />
                <span className="flex-1">{p.action}</span>
                {p.remediation_cost > 0 && <span className="font-mono text-amber-400 whitespace-nowrap">{fmtUsd(p.remediation_cost)}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[9px] text-zinc-600 uppercase tracking-wide border-b border-zinc-800">
              <th className="text-left py-1.5 pr-2">Role</th>
              <th className="text-right px-2">n</th>
              <th className="text-right px-2">Median</th>
              <th className="text-left px-2 w-36">Range</th>
              <th className="text-right px-2">Spread</th>
              <th className="text-right px-2">IQR</th>
              <th className="text-right px-2">Below</th>
              <th className="text-right px-2">$ Fix</th>
              <th className="text-right pl-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {a.roles.map((r) => (
              <tr key={r.title} className="border-b border-zinc-800/30">
                <td className="py-1.5 pr-2 text-zinc-200 truncate max-w-[180px]" title={r.title}>{r.title}</td>
                <td className="px-2 text-right font-mono text-zinc-400">{r.n}</td>
                <td className="px-2 text-right font-mono text-zinc-300">{fmtUsd(r.median)}</td>
                <td className="px-2"><SpreadBar r={r} /></td>
                <td className={`px-2 text-right font-mono ${PE_TONE[r.severity]}`}>{r.spread_pct}%</td>
                <td className="px-2 text-right font-mono text-zinc-500">{r.iqr_pct}%</td>
                <td className="px-2 text-right font-mono text-zinc-400">{r.below_band_n || '—'}</td>
                <td className={`px-2 text-right font-mono ${r.remediation_cost > 0 ? 'text-amber-400' : 'text-zinc-600'}`}>{r.remediation_cost > 0 ? fmtUsd(r.remediation_cost) : '—'}</td>
                <td className="pl-2 text-right"><span className={`text-[10px] font-semibold ${PE_TONE[r.severity]}`}>{PE_LABEL[r.severity]}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-zinc-600 mt-2">Within-role pay dispersion (annualized) — a screen, not a protected-class audit. “Below band” = paid under {a.band_floor_pct}% of the role median; est. remediation lifts them to that floor.</p>
    </div>
  )
}

/* ── pay-equity study register ── */
function PayEquitySection({ reviews, reload }: { reviews: PayEquityReview[]; reload: () => void }) {
  const [show, setShow] = useState(false)
  const [form, setForm] = useState({ review_date: today(), scope: '', gap_pct: '', remediation: '' })
  const [busy, setBusy] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeNote, setAnalyzeNote] = useState<string | null>(null)
  const [analysis, setAnalysis] = useState<PayEquityAnalysisResult | null>(null)
  // live compute-only preview on mount (no study row written)
  useEffect(() => { fetchPayEquityAnalysis().then(setAnalysis).catch(() => setAnalysis(null)) }, [])
  async function add(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await createPayEquityReview({
        review_date: form.review_date || null, scope: form.scope || null,
        gap_pct: form.gap_pct ? parseFloat(form.gap_pct) : null, remediation: form.remediation || null,
      })
      setForm({ review_date: today(), scope: '', gap_pct: '', remediation: '' }); setShow(false); reload()
    } finally { setBusy(false) }
  }
  async function runAnalysis() {
    setAnalyzing(true); setAnalyzeNote(null)
    try {
      const res = await analyzePayEquity()
      const a = res.analysis
      setAnalysis(a)
      setAnalyzeNote(`Logged a study — analyzed ${a.employee_count} employees across ${a.analyzed_roles} roles, ${a.flagged_roles} with excess spread${a.remediation_estimate ? `; ~${fmtUsd(a.remediation_estimate)} to lift ${a.employees_below_band} below-band` : ''}.`)
      reload()
    } catch {
      setAnalyzeNote('Not enough comp data to analyze (need ≥2 employees sharing a role).')
    } finally { setAnalyzing(false) }
  }
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2"><Scale className="h-4 w-4 text-zinc-500" /><h3 className="text-sm font-medium text-zinc-200 tracking-wide">Pay-equity studies</h3></div>
        <div className="flex items-center gap-2">
          <button onClick={runAnalysis} disabled={analyzing} className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 px-2 py-1 rounded-lg border border-emerald-900/60 hover:border-emerald-700 disabled:opacity-50"><Sparkles className="h-3.5 w-3.5" /> {analyzing ? 'Analyzing…' : 'Run analysis from payroll'}</button>
          <button onClick={() => setShow((v) => !v)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700 hover:border-zinc-500"><Plus className="h-3.5 w-3.5" /> Log study</button>
        </div>
      </div>
      <p className="text-[11px] text-zinc-500 mb-3">Run a pay-dispersion analysis from your payroll, or log an external audit. A current study (within cadence) is a named EPL underwriting control; default cadence is annual.</p>
      {analyzeNote && <p className="text-[11px] text-emerald-400/90 mb-3">{analyzeNote}</p>}
      {analysis && <PayEquityReport a={analysis} />}
      {show && (
        <form onSubmit={add} className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4 p-3 rounded-xl bg-zinc-900/60 border border-zinc-800 items-end">
          <div><label className="block text-[10px] text-zinc-500 uppercase mb-1">Study date</label><input type="date" className={inputCls} value={form.review_date} onChange={(e) => setForm({ ...form, review_date: e.target.value })} /></div>
          <input className={inputCls} placeholder="Scope (e.g. all US staff)" value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })} />
          <input className={inputCls} type="number" step="0.1" placeholder="Adj. gap %" value={form.gap_pct} onChange={(e) => setForm({ ...form, gap_pct: e.target.value })} />
          <button type="submit" disabled={busy} className="bg-zinc-100 text-zinc-900 text-sm font-medium rounded-lg px-3 py-1.5 hover:bg-white disabled:opacity-50">{busy ? '…' : 'Add'}</button>
          <input className={`${inputCls} md:col-span-4`} placeholder="Remediation taken (optional)" value={form.remediation} onChange={(e) => setForm({ ...form, remediation: e.target.value })} />
        </form>
      )}
      {reviews.length === 0 ? <p className="text-sm text-zinc-500">No pay-equity studies logged. Logging one flips this from broker-attested to data-derived in your EPL profile.</p> : (
        <div className="space-y-1">
          {reviews.map((r) => (
            <div key={r.id} className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
              <span className="text-sm text-zinc-200 w-28 shrink-0">{r.review_date ?? '—'}</span>
              <span className="text-sm text-zinc-400 flex-1 min-w-0 truncate">{r.scope || 'Pay-equity study'}{r.gap_pct != null && <span className="text-[11px] text-zinc-600 ml-2">{r.gap_pct}% gap</span>}</span>
              <span className="text-[11px] text-zinc-500">due {r.next_due_date ?? '—'}</span>
              {r.is_overdue && <span className="inline-flex items-center gap-1 text-[11px] text-red-400"><AlertTriangle className="h-3 w-3" /> overdue</span>}
              {!r.is_overdue && <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400"><Check className="h-3 w-3" /> current</span>}
              <button onClick={() => deletePayEquityReview(r.id).then(reload)} className="text-zinc-600 hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
