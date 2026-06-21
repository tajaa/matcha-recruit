import { useEffect, useState, type FormEvent } from 'react'
import { ShieldCheck, Bot, Fingerprint, Plus, Trash2, Loader2, AlertTriangle, Check } from 'lucide-react'
import { Card } from '../../components/ui'
import {
  fetchAiAudits, createAiAudit, updateAiAudit, deleteAiAudit,
  fetchBiometricPoints, createBiometricPoint, updateBiometricPoint, deleteBiometricPoint,
  fetchPayTransparency, setPayTransparency,
} from '../../api/workforceCompliance'
import type {
  AiAudit, BiometricPoint, PayTransparencyRow, PayTransparencyStatus, CollectionType,
} from '../../types/workforceCompliance'

const today = () => new Date().toISOString().slice(0, 10)
const inputCls = 'w-full bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500'
const PT_TONE: Record<string, string> = { compliant: 'text-emerald-400', action_needed: 'text-red-400', na: 'text-zinc-500' }
const COLLECTION_TYPES: CollectionType[] = ['fingerprint', 'face', 'iris', 'voice', 'hand_geometry', 'other']

export default function WorkforceCompliance() {
  const [audits, setAudits] = useState<AiAudit[]>([])
  const [points, setPoints] = useState<BiometricPoint[]>([])
  const [pt, setPt] = useState<PayTransparencyRow[]>([])
  const [loading, setLoading] = useState(true)

  function load() {
    setLoading(true)
    Promise.allSettled([
      fetchAiAudits().then(setAudits),
      fetchBiometricPoints().then(setPoints),
      fetchPayTransparency().then(setPt),
    ]).finally(() => setLoading(false))
  }
  useEffect(load, [])

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  }

  const ptAction = pt.filter((r) => r.required && r.status !== 'compliant').length
  const overdue = audits.filter((a) => a.is_overdue).length
  const missingConsent = points.filter((p) => p.is_active && !p.consent_obtained).length

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-zinc-400" /> Workforce Compliance
        </h1>
        <p className="text-sm text-zinc-500 mt-1">Employment-practices risk controls — pay transparency, AI hiring-tool audits, and biometric consent. Tracked for your own compliance; also strengthens your EPL insurance profile.</p>
      </div>

      {/* Summary strip */}
      <div className="grid grid-cols-3 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
        {[
          { label: 'Pay-Transparency · Action', value: ptAction },
          { label: 'AI Audits · Overdue', value: overdue },
          { label: 'Biometric · Missing Consent', value: missingConsent },
        ].map((c) => (
          <div key={c.label} className="bg-zinc-900 px-4 py-4">
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{c.label}</div>
            <div className={`text-2xl font-light font-mono mt-1.5 ${c.value > 0 ? 'text-red-400' : 'text-emerald-400'}`}>{c.value}</div>
          </div>
        ))}
      </div>

      <PayTransparencySection rows={pt} onChange={setPt} />
      <AiAuditSection audits={audits} reload={load} />
      <BiometricSection points={points} reload={load} />
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
        <button onClick={() => setShow((v) => !v)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700 hover:border-zinc-500"><Plus className="h-3.5 w-3.5" /> Add tool</button>
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
        <button onClick={() => setShow((v) => !v)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700 hover:border-zinc-500"><Plus className="h-3.5 w-3.5" /> Add</button>
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
