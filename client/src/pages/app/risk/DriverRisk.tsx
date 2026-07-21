import { useState } from 'react'
import { Car, FileDown, Loader2, Plus, Trash2, ChevronDown, Check, AlertTriangle } from 'lucide-react'
import { Card, MetricStrip } from '../../../components/ui'
import { useAsync } from '../../../hooks/useAsync'
import { RegisterSpinner } from '../../../components/register/registerKit'
import { fetchFleet, createDriver, updateDriver, deleteDriver, downloadFleetPdf } from '../../../api/risk/driverRisk'
import type { Fleet, DriverRow, DriverPayload, DriverTier, LicenseStatus, ReviewType, MvrStatus } from '../../../types/driverRisk'
import { TIER_TONE, TIER_LABEL, GRADE_TONE } from '../../../types/driverRisk'

const LICENSE: LicenseStatus[] = ['valid', 'suspended', 'expired', 'unknown']
const RTYPE: ReviewType[] = ['hire', 'annual', 'post_incident', 'periodic']
const STATUS: MvrStatus[] = ['clear', 'flagged', 'pending']

export default function DriverRisk() {
  const [dl, setDl] = useState(false)
  const [adding, setAdding] = useState(false)

  const { data: fleet, loading, setData: setFleet } = useAsync(() => fetchFleet(), [])

  async function download() {
    setDl(true)
    try { await downloadFleetPdf() } finally { setDl(false) }
  }

  if (loading) return <RegisterSpinner />
  if (!fleet) return <p className="text-sm text-zinc-500">Unable to load driver risk.</p>

  const s = fleet.summary
  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
            <Car className="h-5 w-5 text-zinc-400" /> Driver Risk
          </h1>
          <p className="text-sm text-zinc-500 mt-1 max-w-2xl">Track each driver's MVR (license status, violations, accidents) → an at-a-glance fleet risk grade. The #1 commercial-auto underwriting input — a clean, documented fleet buys down auto premium.</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={() => setAdding((v) => !v)} className="inline-flex items-center gap-1 text-sm text-zinc-300 hover:text-zinc-100 px-3 py-2 rounded-lg border border-zinc-700"><Plus className="h-4 w-4" /> Add driver</button>
          <button onClick={download} disabled={dl} className="inline-flex items-center gap-1.5 text-sm text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-2 font-medium disabled:opacity-50">
            {dl ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />} Driver-risk PDF
          </button>
        </div>
      </div>

      <MetricStrip cols="grid-cols-2 md:grid-cols-5">
        <Stat label="Fleet grade" value={s.grade} tone={GRADE_TONE[s.grade] ?? 'text-zinc-200'} />
        <Stat label="Drivers" value={s.total_drivers} tone="text-zinc-200" />
        <Stat label="Clean" value={s.clean} tone="text-emerald-400" />
        <Stat label="High risk" value={s.high_risk} tone={s.high_risk ? 'text-red-400' : 'text-zinc-200'} />
        <Stat label="Overdue MVR" value={s.overdue_reviews} tone={s.overdue_reviews ? 'text-amber-400' : 'text-zinc-200'} />
      </MetricStrip>

      {adding && (
        <Card className="p-4">
          <DriverForm onDone={(f) => { setFleet(f); setAdding(false) }} onCancel={() => setAdding(false)} />
        </Card>
      )}

      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-3">Drivers</h3>
        {fleet.drivers.length === 0 ? (
          <p className="text-sm text-zinc-600">No drivers yet — add one to start scoring the fleet.</p>
        ) : (
          <div className="space-y-1">
            {fleet.drivers.map((d) => <DriverRowItem key={d.id} d={d} onChange={setFleet} />)}
          </div>
        )}
      </Card>
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: number | string; tone: string }) {
  return (
    <div className="bg-zinc-900 px-4 py-4">
      <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{label}</div>
      <div className={`text-2xl font-light font-mono mt-1.5 ${tone}`}>{value}</div>
    </div>
  )
}

function DriverRowItem({ d, onChange }: { d: DriverRow; onChange: (f: Fleet) => void }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  async function remove() {
    setBusy(true)
    try { onChange(await deleteDriver(d.id)) } finally { setBusy(false) }
  }

  return (
    <div className="border-b border-zinc-800/30 last:border-0">
      <div className="flex items-center gap-3 py-2">
        <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase shrink-0 ${TIER_TONE[d.tier as DriverTier]}`}>{TIER_LABEL[d.tier as DriverTier]}</span>
        <div className="flex-1 min-w-0">
          <div className="text-sm text-zinc-200 flex items-center gap-2">
            {d.driver_name}
            {d.license_status !== 'valid' && <span className="text-[10px] text-red-400 uppercase">{d.license_status}</span>}
          </div>
          <div className="text-[11px] text-zinc-500 truncate">
            {d.violation_count} viol · {d.accident_count} acc{d.major_violation ? ' · major' : ''} · last MVR {d.review_date || '—'}
            {d.overdue ? <span className="text-amber-400"> · MVR overdue</span> : d.next_due_date ? ` · due ${d.next_due_date}` : ''}
          </div>
        </div>
        <button onClick={() => setOpen((v) => !v)} className="text-zinc-500 hover:text-zinc-200 p-1 shrink-0"><ChevronDown className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`} /></button>
        <button onClick={remove} disabled={busy} className="text-zinc-600 hover:text-red-400 p-1 shrink-0"><Trash2 className="h-4 w-4" /></button>
      </div>
      {open && (
        <div className="pb-3 px-1">
          <DriverForm existing={d} onDone={(f) => { onChange(f); setOpen(false) }} onCancel={() => setOpen(false)} />
        </div>
      )}
    </div>
  )
}

function DriverForm({ existing, onDone, onCancel }: { existing?: DriverRow; onDone: (f: Fleet) => void; onCancel: () => void }) {
  const [name, setName] = useState(existing?.driver_name ?? '')
  const [license, setLicense] = useState<LicenseStatus>(existing?.license_status ?? 'valid')
  const [rtype, setRtype] = useState<ReviewType>(existing?.review_type ?? 'annual')
  const [reviewDate, setReviewDate] = useState(existing?.review_date ?? '')
  const [nextDue, setNextDue] = useState(existing?.next_due_date ?? '')
  const [status, setStatus] = useState<MvrStatus>(existing?.status ?? 'pending')
  const [viol, setViol] = useState(String(existing?.violation_count ?? 0))
  const [acc, setAcc] = useState(String(existing?.accident_count ?? 0))
  const [major, setMajor] = useState(existing?.major_violation ?? false)
  const [notes, setNotes] = useState(existing?.notes ?? '')
  const [busy, setBusy] = useState(false)

  const int = (s: string) => Math.max(0, Math.round(Number(s) || 0))

  async function save() {
    if (!name.trim()) return
    setBusy(true)
    const payload: DriverPayload = {
      driver_name: name.trim(), license_status: license, review_type: rtype,
      review_date: reviewDate || null, next_due_date: nextDue || null, status,
      violation_count: int(viol), accident_count: int(acc), major_violation: major, notes: notes || null,
    }
    try {
      onDone(existing ? await updateDriver(existing.id, payload) : await createDriver({ ...payload, driver_name: name.trim() }))
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Field label="Driver name"><input value={name} onChange={(e) => setName(e.target.value)} className={inputCls} /></Field>
        <Field label="License"><select value={license} onChange={(e) => setLicense(e.target.value as LicenseStatus)} className={inputCls}>{LICENSE.map((l) => <option key={l} value={l}>{l}</option>)}</select></Field>
        <Field label="Moving violations"><input value={viol} onChange={(e) => setViol(e.target.value)} className={inputCls} /></Field>
        <Field label="At-fault accidents"><input value={acc} onChange={(e) => setAcc(e.target.value)} className={inputCls} /></Field>
        <Field label="Review type"><select value={rtype} onChange={(e) => setRtype(e.target.value as ReviewType)} className={inputCls}>{RTYPE.map((t) => <option key={t} value={t}>{t}</option>)}</select></Field>
        <Field label="MVR status"><select value={status} onChange={(e) => setStatus(e.target.value as MvrStatus)} className={inputCls}>{STATUS.map((t) => <option key={t} value={t}>{t}</option>)}</select></Field>
        <Field label="Last review date"><input type="date" value={reviewDate} onChange={(e) => setReviewDate(e.target.value)} className={inputCls} /></Field>
        <Field label="Next due date"><input type="date" value={nextDue} onChange={(e) => setNextDue(e.target.value)} className={inputCls} /></Field>
      </div>
      <label className="inline-flex items-center gap-1.5 text-xs text-zinc-300 cursor-pointer">
        <input type="checkbox" checked={major} onChange={(e) => setMajor(e.target.checked)} className="rounded border-zinc-600 bg-zinc-900 text-emerald-500 focus:ring-0" />
        <AlertTriangle className="h-3.5 w-3.5 text-amber-500" /> Major violation (DUI / reckless / suspension)
      </label>
      <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Notes (optional)" className={`${inputCls} w-full`} />
      <div className="flex items-center gap-2">
        <button onClick={save} disabled={busy || !name.trim()} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-3 py-1.5 disabled:opacity-50">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Save
        </button>
        <button onClick={onCancel} className="text-xs text-zinc-400 hover:text-zinc-100 px-3 py-1.5 rounded-lg border border-zinc-700">Cancel</button>
      </div>
    </div>
  )
}

const inputCls = 'bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 w-full'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[10px] text-zinc-500 uppercase tracking-wide">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  )
}
