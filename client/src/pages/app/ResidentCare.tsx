import { useEffect, useState, type FormEvent } from 'react'
import { HeartPulse, ShieldPlus, Car, Plus, Trash2, Loader2, AlertTriangle, Check, FileDown } from 'lucide-react'
import { Card } from '../../components/ui'
import {
  fetchResidentCareSummary, fetchSafetyPrograms, createSafetyProgram, deleteSafetyProgram, suggestSafetyPrograms,
  fetchMvrReviews, createMvrReview, updateMvrReview, deleteMvrReview, downloadResidentCareAsset,
} from '../../api/residentCare'
import type { SafetyProgram, MvrReview, ResidentCareSummary, ProgramType, MvrStatus } from '../../types/residentCare'
import { PROGRAM_LABELS, PROGRAM_TYPES } from '../../types/residentCare'
import { AiSuggest } from '../../components/AiSuggest'

const today = () => new Date().toISOString().slice(0, 10)
const inputCls = 'w-full bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500'
const MVR_TONE: Record<MvrStatus, string> = { clear: 'text-emerald-400', flagged: 'text-red-400', pending: 'text-amber-400' }

export default function ResidentCare() {
  const [summary, setSummary] = useState<ResidentCareSummary | null>(null)
  const [programs, setPrograms] = useState<SafetyProgram[]>([])
  const [mvr, setMvr] = useState<MvrReview[]>([])
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)

  function load() {
    setLoading(true)
    Promise.allSettled([
      fetchResidentCareSummary().then(setSummary),
      fetchSafetyPrograms().then(setPrograms),
      fetchMvrReviews().then(setMvr),
    ]).finally(() => setLoading(false))
  }
  useEffect(load, [])

  async function download() {
    setDownloading(true)
    try { await downloadResidentCareAsset() } finally { setDownloading(false) }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
            <HeartPulse className="h-5 w-5 text-zinc-400" /> Resident-Care Risk
          </h1>
          <p className="text-sm text-zinc-500 mt-1">Your resident-care risk-management program — safety programs, MVR reviews, and credentialing currency. A documented program is a valuable asset to highlight for prospective insurers.</p>
        </div>
        <button onClick={download} disabled={downloading} className="inline-flex items-center gap-1.5 text-sm text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-2 font-medium disabled:opacity-50 shrink-0">
          {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />} Insurer asset
        </button>
      </div>

      {/* Summary strip */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
          <Stat label="Active programs" value={summary.programs.active} good={summary.programs.active > 0} />
          <Stat label="MVR current" value={`${summary.mvr.current}/${summary.mvr.total}`} good={summary.mvr.overdue === 0} />
          <Stat label="MVR overdue" value={summary.mvr.overdue} good={summary.mvr.overdue === 0} invert />
          <Stat label="Credentialing" value={summary.credentialing.current_pct != null ? `${summary.credentialing.current_pct}%` : '—'} good={(summary.credentialing.current_pct ?? 100) >= 90} />
        </div>
      )}

      <SafetyProgramsSection programs={programs} reload={load} />
      <MvrSection reviews={mvr} reload={load} />
    </div>
  )
}

function Stat({ label, value, good, invert }: { label: string; value: number | string; good: boolean; invert?: boolean }) {
  const tone = invert ? (good ? 'text-emerald-400' : 'text-red-400') : (good ? 'text-emerald-400' : 'text-amber-400')
  return (
    <div className="bg-zinc-900 px-4 py-4">
      <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{label}</div>
      <div className={`text-2xl font-light font-mono mt-1.5 ${tone}`}>{value}</div>
    </div>
  )
}

/* ── safety programs ── */
function SafetyProgramsSection({ programs, reload }: { programs: SafetyProgram[]; reload: () => void }) {
  const [show, setShow] = useState(false)
  const [form, setForm] = useState<{ program_type: ProgramType; name: string; owner: string }>({ program_type: 'fall_prevention', name: '', owner: '' })
  const [busy, setBusy] = useState(false)
  async function add(e: FormEvent) {
    e.preventDefault()
    if (!form.name.trim()) return
    setBusy(true)
    try {
      await createSafetyProgram({ program_type: form.program_type, name: form.name.trim(), owner: form.owner || null, last_reviewed_date: today() })
      setForm({ program_type: 'fall_prevention', name: '', owner: '' }); setShow(false); reload()
    } finally { setBusy(false) }
  }
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2"><ShieldPlus className="h-4 w-4 text-zinc-500" /><h3 className="text-sm font-medium text-zinc-200 tracking-wide">Safety &amp; risk-management programs</h3></div>
        <div className="flex items-center gap-2">
          <AiSuggest
            fetchSuggestions={suggestSafetyPrograms}
            itemLabel={(s) => `${PROGRAM_LABELS[s.program_type]} — ${s.name}`}
            createItem={(s) => createSafetyProgram({ program_type: s.program_type, name: s.name })}
            onDone={reload}
          />
          <button onClick={() => setShow((v) => !v)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700 hover:border-zinc-500"><Plus className="h-3.5 w-3.5" /> Add program</button>
        </div>
      </div>
      <p className="text-[11px] text-zinc-500 mb-3">Document each formal program (fall-prevention, infection-control, abuse-prevention, …). Underwriters credit a strong documented program.</p>
      {show && (
        <form onSubmit={add} className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4 p-3 rounded-xl bg-zinc-900/60 border border-zinc-800 items-end">
          <div><label className="block text-[10px] text-zinc-500 uppercase mb-1">Type</label>
            <select className={inputCls} value={form.program_type} onChange={(e) => setForm({ ...form, program_type: e.target.value as ProgramType })}>
              {PROGRAM_TYPES.map((t) => <option key={t} value={t}>{PROGRAM_LABELS[t]}</option>)}
            </select></div>
          <input className={inputCls} placeholder="Program name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className={inputCls} placeholder="Owner" value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} />
          <button type="submit" disabled={busy} className="bg-zinc-100 text-zinc-900 text-sm font-medium rounded-lg px-3 py-1.5 hover:bg-white disabled:opacity-50">{busy ? '…' : 'Add'}</button>
        </form>
      )}
      {programs.length === 0 ? <p className="text-sm text-zinc-500">No safety programs documented yet.</p> : (
        <div className="space-y-1">
          {programs.map((p) => (
            <div key={p.id} className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
              <span className="text-[11px] text-zinc-500 w-36 shrink-0">{PROGRAM_LABELS[p.program_type]}</span>
              <span className="text-sm text-zinc-200 flex-1">{p.name}{p.owner && <span className="text-[11px] text-zinc-600 ml-2">{p.owner}</span>}</span>
              <span className={`text-[11px] font-semibold uppercase ${p.status === 'active' ? 'text-emerald-400' : 'text-zinc-600'}`}>{p.status}</span>
              <button onClick={() => deleteSafetyProgram(p.id).then(reload)} className="text-zinc-600 hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

/* ── MVR reviews ── */
function MvrSection({ reviews, reload }: { reviews: MvrReview[]; reload: () => void }) {
  const [show, setShow] = useState(false)
  const [form, setForm] = useState<{ driver_name: string; review_type: 'hire' | 'annual'; status: MvrStatus }>({ driver_name: '', review_type: 'annual', status: 'clear' })
  const [busy, setBusy] = useState(false)
  const overdue = (m: MvrReview) => m.next_due_date != null && m.next_due_date < today()
  async function add(e: FormEvent) {
    e.preventDefault()
    if (!form.driver_name.trim()) return
    setBusy(true)
    try {
      await createMvrReview({ driver_name: form.driver_name.trim(), review_type: form.review_type, status: form.status, review_date: today() })
      setForm({ driver_name: '', review_type: 'annual', status: 'clear' }); setShow(false); reload()
    } finally { setBusy(false) }
  }
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2"><Car className="h-4 w-4 text-zinc-500" /><h3 className="text-sm font-medium text-zinc-200 tracking-wide">MVR reviews</h3></div>
        <button onClick={() => setShow((v) => !v)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700 hover:border-zinc-500"><Plus className="h-3.5 w-3.5" /> Add review</button>
      </div>
      <p className="text-[11px] text-zinc-500 mb-3">Motor-vehicle-record reviews at hire and annually for any driving staff — a named auto-liability control.</p>
      {show && (
        <form onSubmit={add} className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4 p-3 rounded-xl bg-zinc-900/60 border border-zinc-800 items-end">
          <input className={inputCls} placeholder="Driver name" value={form.driver_name} onChange={(e) => setForm({ ...form, driver_name: e.target.value })} />
          <div><label className="block text-[10px] text-zinc-500 uppercase mb-1">Type</label>
            <select className={inputCls} value={form.review_type} onChange={(e) => setForm({ ...form, review_type: e.target.value as 'hire' | 'annual' })}>
              <option value="annual">Annual</option><option value="hire">At hire</option>
            </select></div>
          <div><label className="block text-[10px] text-zinc-500 uppercase mb-1">Result</label>
            <select className={inputCls} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as MvrStatus })}>
              <option value="clear">Clear</option><option value="flagged">Flagged</option><option value="pending">Pending</option>
            </select></div>
          <button type="submit" disabled={busy} className="bg-zinc-100 text-zinc-900 text-sm font-medium rounded-lg px-3 py-1.5 hover:bg-white disabled:opacity-50">{busy ? '…' : 'Add'}</button>
        </form>
      )}
      {reviews.length === 0 ? <p className="text-sm text-zinc-500">No MVR reviews on file.</p> : (
        <div className="space-y-1">
          {reviews.map((m) => (
            <div key={m.id} className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
              <span className="text-sm text-zinc-200 flex-1">{m.driver_name}<span className="text-[11px] text-zinc-600 ml-2">{m.review_type}</span></span>
              <span className="text-[11px] text-zinc-500">due {m.next_due_date ?? '—'}</span>
              {overdue(m) && <span className="inline-flex items-center gap-1 text-[11px] text-red-400"><AlertTriangle className="h-3 w-3" /> overdue</span>}
              <span className={`inline-flex items-center gap-1 text-[11px] font-semibold uppercase ${MVR_TONE[m.status]}`}>{m.status === 'clear' && <Check className="h-3 w-3" />}{m.status}</span>
              <button onClick={() => updateMvrReview(m.id, { review_date: today(), status: 'clear', next_due_date: new Date(Date.now() + 365 * 864e5).toISOString().slice(0, 10) }).then(reload)} className="text-xs text-zinc-300 hover:text-emerald-400 px-2 py-1 rounded-lg border border-zinc-700">Mark reviewed</button>
              <button onClick={() => deleteMvrReview(m.id).then(reload)} className="text-zinc-600 hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
