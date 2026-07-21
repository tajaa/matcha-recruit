import { useEffect, useState, useCallback } from 'react'
import {
  CalendarDays, Loader2, Plus, Trash2, ChevronLeft, ChevronRight, Check, X,
  Send, Users, LayoutTemplate, Inbox, Sparkles,
} from 'lucide-react'
import { Card, useToast } from '../../../components/ui'
import { ApiError } from '../../../api/client'
import {
  createShift, deleteShift, publishShift,
  assignEmployee, unassignEmployee, fetchTemplates, createTemplate, deleteTemplate,
  generateFromTemplate, fetchRequests, reviewRequest,
} from '../../../api/employees/employeeSchedule'
import type {
  Shift, RosterEmployee, ShiftTemplate, ScheduleRequest, ShiftPayload,
} from '../../../types/employeeSchedule'
import {
  STATUS_TONE, REQUEST_TONE, errorMessage,
  fmtTime, fmtDayLabel, toISODate, addDays, startOfWeekSunday,
} from '../../../types/employeeSchedule'
import { useEmployeeSchedule } from './useEmployeeSchedule'

const inputCls = 'bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 w-full'

const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

interface ComplianceViolation {
  check: string
  severity: string
  message: string
  statute?: string | null
}

interface ForceableDetail {
  code?: string
  message?: string
  conflicts?: { starts_at: string; ends_at: string; role: string | null }[]
  violations?: ComplianceViolation[]
}

/** A 409 the admin can override → confirm() text. Anything else → null (it gets
 *  surfaced as an error instead of silently swallowed). */
function conflictPrompt(err: unknown): string | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null
  const detail = (err.body as { detail?: ForceableDetail } | null)?.detail
  if (detail?.code === 'schedule_conflict') {
    const lines = (detail.conflicts ?? []).map(
      (c) => `• ${fmtDayLabel(c.starts_at)} ${fmtTime(c.starts_at)}–${fmtTime(c.ends_at)}${c.role ? ` (${c.role})` : ''}`,
    )
    return `Already scheduled during this time:\n${lines.join('\n')}\n\nAssign anyway?`
  }
  if (detail?.code === 'shift_full') {
    return `${detail.message ?? 'This shift is already fully staffed.'}\n\nAssign anyway?`
  }
  if (detail?.code === 'schedule_compliance') {
    // Advisory scheduling-law flags (meal break, overtime, min rest). A hard
    // minor-hour limit comes back as a 422 (schedule_compliance_block) instead
    // and is surfaced as a non-overridable error by errorMessage().
    const lines = (detail.violations ?? []).map(
      (v) => `• ${v.message}${v.statute ? ` [${v.statute}]` : ''}`,
    )
    return `This shift may not comply with scheduling law:\n${lines.join('\n')}\n\nSchedule anyway?`
  }
  return null
}

export default function EmployeeSchedule() {
  const {
    tab, setTab,
    weekStart, setWeekStart,
    shifts,
    roster,
    summary,
    loading,
    publishing,
    reload,
    patchShift,
    publishWeek,
    days,
  } = useEmployeeSchedule()

  return (
    // Same page frame as Compliance/Dashboard/Onboarding/Company/OSHA Logs.
    // Tab STYLE kept as-is (icon + label, underline) rather than switched to
    // the compact mono tabs those pages use — it's already a deliberate,
    // working motif here, not a chunky-button substitute like Compliance's
    // Button-pills were. Only the shell + tab band placement change.
    <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
      <div className="border-b border-white/[0.06] px-5 py-4">
        <h1 className="text-2xl font-light tracking-tight text-zinc-50 flex items-center gap-2">
          <CalendarDays className="h-5 w-5 text-zinc-500" /> Employee Schedule
        </h1>
        <p className="text-sm text-zinc-500 mt-1 max-w-2xl">Build weekly shifts over your roster, assign employees, and publish. Generate recurring weeks from reusable templates. Employees see published shifts and can request swaps or time off.</p>
      </div>

      <div className="flex items-center gap-1 border-b border-white/[0.06] px-5">
        <TabButton active={tab === 'schedule'} onClick={() => setTab('schedule')} icon={<CalendarDays className="h-4 w-4" />}>Schedule</TabButton>
        <TabButton active={tab === 'templates'} onClick={() => setTab('templates')} icon={<LayoutTemplate className="h-4 w-4" />}>Templates</TabButton>
        <TabButton active={tab === 'requests'} onClick={() => setTab('requests')} icon={<Inbox className="h-4 w-4" />}>Requests</TabButton>
      </div>

      <div className="p-5 space-y-6">

      {tab === 'schedule' && (
        <>
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-2">
              <button onClick={() => setWeekStart((w) => addDays(w, -7))} className="text-zinc-400 hover:text-zinc-100 p-1.5 rounded-lg border border-white/[0.08]"><ChevronLeft className="h-4 w-4" /></button>
              <button onClick={() => setWeekStart(toISODate(startOfWeekSunday(new Date())))} className="text-sm text-zinc-300 hover:text-zinc-100 px-3 py-1.5 rounded-lg border border-white/[0.08]">This week</button>
              <button onClick={() => setWeekStart((w) => addDays(w, 7))} className="text-zinc-400 hover:text-zinc-100 p-1.5 rounded-lg border border-white/[0.08]"><ChevronRight className="h-4 w-4" /></button>
              <span className="text-sm text-zinc-500 ml-1">Week of {fmtDayLabel(weekStart)}</span>
            </div>
            <button onClick={publishWeek} disabled={publishing || !summary?.draft} className="inline-flex items-center gap-1.5 text-sm text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-2 font-medium disabled:opacity-40">
              {publishing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Publish week{summary?.draft ? ` (${summary.draft})` : ''}
            </button>
          </div>

          {summary && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-white/[0.06] border border-white/[0.06] rounded-lg overflow-hidden">
              <Stat label="Shifts" value={summary.total_shifts} tone="text-zinc-200" />
              <Stat label="Published" value={summary.published} tone="text-emerald-400" />
              <Stat label="Draft" value={summary.draft} tone={summary.draft ? 'text-amber-400' : 'text-zinc-200'} />
              <Stat label="Open" value={summary.open_shifts} tone={summary.open_shifts ? 'text-amber-400' : 'text-zinc-200'} />
              <Stat label="Assigned" value={summary.assigned} tone="text-zinc-200" />
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-7 gap-3">
              {days.map((day) => (
                <DayColumn
                  key={day}
                  day={day}
                  shifts={shifts.filter((s) => s.starts_at.slice(0, 10) === day)}
                  roster={roster}
                  onPatch={patchShift}
                  onChanged={reload}
                />
              ))}
            </div>
          )}
        </>
      )}

      {tab === 'templates' && <TemplatesTab onGenerated={() => { setTab('schedule'); reload() }} />}
      {tab === 'requests' && <RequestsTab onReviewed={reload} />}
      </div>
    </div>
  )
}

function TabButton({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className={`inline-flex items-center gap-1.5 px-3 py-2 text-sm border-b-2 -mb-px transition-colors ${active ? 'border-emerald-500 text-zinc-100' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}>
      {icon}{children}
    </button>
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

function DayColumn({ day, shifts, roster, onPatch, onChanged }: {
  day: string; shifts: Shift[]; roster: RosterEmployee[]; onPatch: (s: Shift) => void; onChanged: () => void
}) {
  const [adding, setAdding] = useState(false)
  return (
    <div className="min-w-0">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wide">{fmtDayLabel(day)}</span>
        <button onClick={() => setAdding((v) => !v)} className="text-zinc-500 hover:text-zinc-200 p-0.5"><Plus className="h-3.5 w-3.5" /></button>
      </div>
      <div className="space-y-2">
        {adding && (
          <Card className="p-2.5">
            <ShiftForm day={day} onDone={() => { setAdding(false); onChanged() }} onCancel={() => setAdding(false)} />
          </Card>
        )}
        {shifts.length === 0 && !adding && <p className="text-[11px] text-zinc-700 py-2">No shifts</p>}
        {shifts.map((s) => (
          <ShiftCard key={s.id} shift={s} roster={roster} onPatch={onPatch} onChanged={onChanged} />
        ))}
      </div>
    </div>
  )
}

function ShiftCard({ shift, roster, onPatch, onChanged }: {
  shift: Shift; roster: RosterEmployee[]; onPatch: (s: Shift) => void; onChanged: () => void
}) {
  const { toast } = useToast()
  const [busy, setBusy] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const assignedIds = new Set(shift.assignments.map((a) => a.employee_id))
  const available = roster.filter((e) => !assignedIds.has(e.id))
  const understaffed = shift.assignments.length < shift.required_staff

  async function act(fn: () => Promise<Shift>) {
    setBusy(true)
    try { onPatch(await fn()) } catch (err) { toast(errorMessage(err), 'error') } finally { setBusy(false) }
  }
  async function assign(employeeId: string) {
    setBusy(true)
    try {
      onPatch(await assignEmployee(shift.id, employeeId))
    } catch (err) {
      const prompt = conflictPrompt(err)
      if (!prompt) {
        // 403 (feature gate), 404 (stale roster), 409 (cancelled shift), 500 —
        // all used to vanish, leaving the admin staring at an unassigned shift.
        toast(errorMessage(err), 'error')
      } else if (window.confirm(prompt)) {
        try {
          onPatch(await assignEmployee(shift.id, employeeId, true))
        } catch (forcedErr) {
          toast(errorMessage(forcedErr), 'error')
        }
      }
    } finally { setBusy(false) }
  }
  async function remove() {
    setBusy(true)
    try { await deleteShift(shift.id); onChanged() } catch (err) { toast(errorMessage(err), 'error') } finally { setBusy(false) }
  }

  return (
    <div className={`rounded-lg border p-2.5 ${shift.status === 'cancelled' ? 'border-red-500/20 bg-red-500/5 opacity-70' : 'border-zinc-800 bg-zinc-900/60'}`}>
      <div className="flex items-center justify-between gap-1">
        <span className="text-sm font-medium text-zinc-100">{fmtTime(shift.starts_at)}–{fmtTime(shift.ends_at)}</span>
        <span className={`px-1.5 py-0.5 rounded-full border text-[9px] font-semibold uppercase ${STATUS_TONE[shift.status]}`}>{shift.status}</span>
      </div>
      {(shift.role || shift.department) && (
        <div className="text-[11px] text-zinc-400 mt-0.5 truncate">{[shift.role, shift.department].filter(Boolean).join(' · ')}</div>
      )}
      <div className="mt-2 flex flex-wrap gap-1">
        {shift.assignments.map((a) => (
          <span key={a.employee_id} className="inline-flex items-center gap-1 bg-zinc-800 rounded-full pl-2 pr-1 py-0.5 text-[11px] text-zinc-200">
            {a.name}
            <button onClick={() => act(() => unassignEmployee(shift.id, a.employee_id))} disabled={busy} className="text-zinc-500 hover:text-red-400"><X className="h-3 w-3" /></button>
          </span>
        ))}
        <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${understaffed ? 'text-amber-400 bg-amber-500/10' : 'text-emerald-400 bg-emerald-500/10'}`}>
          {shift.assignments.length}/{shift.required_staff}
        </span>
      </div>

      {pickerOpen && available.length > 0 && (
        <select
          className={`${inputCls} mt-2 text-xs`}
          value=""
          onChange={(e) => { if (e.target.value) { assign(e.target.value); setPickerOpen(false) } }}
        >
          <option value="">Select employee…</option>
          {available.map((e) => <option key={e.id} value={e.id}>{e.name}{e.job_title ? ` — ${e.job_title}` : ''}</option>)}
        </select>
      )}

      <div className="mt-2 flex items-center gap-2">
        <button onClick={() => setPickerOpen((v) => !v)} disabled={busy || available.length === 0} className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-100 disabled:opacity-40"><Users className="h-3 w-3" /> Assign</button>
        {shift.status === 'draft' && (
          <button onClick={() => act(() => publishShift(shift.id))} disabled={busy} className="inline-flex items-center gap-1 text-[11px] text-emerald-400 hover:text-emerald-300"><Send className="h-3 w-3" /> Publish</button>
        )}
        <button onClick={remove} disabled={busy} className="inline-flex items-center gap-1 text-[11px] text-zinc-600 hover:text-red-400 ml-auto"><Trash2 className="h-3 w-3" /></button>
      </div>
    </div>
  )
}

function ShiftForm({ day, onDone, onCancel }: { day: string; onDone: () => void; onCancel: () => void }) {
  const [start, setStart] = useState('09:00')
  const [end, setEnd] = useState('17:00')
  const [role, setRole] = useState('')
  const [required, setRequired] = useState('1')
  const [busy, setBusy] = useState(false)

  async function save() {
    setBusy(true)
    try {
      const endDay = end <= start ? addDays(day, 1) : day
      const payload: ShiftPayload = {
        starts_at: `${day}T${start}:00Z`,
        ends_at: `${endDay}T${end}:00Z`,
        role: role.trim() || null,
        required_staff: Math.max(1, Math.round(Number(required) || 1)),
      }
      await createShift(payload)
      onDone()
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-1.5">
      <div className="grid grid-cols-2 gap-1.5">
        <input type="time" value={start} onChange={(e) => setStart(e.target.value)} className={inputCls} />
        <input type="time" value={end} onChange={(e) => setEnd(e.target.value)} className={inputCls} />
      </div>
      <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Role (optional)" className={inputCls} />
      <input value={required} onChange={(e) => setRequired(e.target.value)} placeholder="Staff needed" className={inputCls} />
      <div className="flex items-center gap-1.5">
        <button onClick={save} disabled={busy} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-2.5 py-1.5 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Add</button>
        <button onClick={onCancel} className="text-xs text-zinc-400 hover:text-zinc-100 px-2.5 py-1.5 rounded-lg border border-zinc-700">Cancel</button>
      </div>
    </div>
  )
}

// ---------- Templates tab ----------

function TemplatesTab({ onGenerated }: { onGenerated: () => void }) {
  const [templates, setTemplates] = useState<ShiftTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)

  const load = useCallback(() => fetchTemplates().then((r) => setTemplates(r.templates)), [])
  useEffect(() => { load().finally(() => setLoading(false)) }, [load])

  if (loading) return <div className="flex items-center justify-center h-40"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-zinc-200">Shift templates</h3>
        <button onClick={() => setAdding((v) => !v)} className="inline-flex items-center gap-1 text-sm text-zinc-300 hover:text-zinc-100 px-3 py-1.5 rounded-lg border border-zinc-700"><Plus className="h-4 w-4" /> New template</button>
      </div>
      {adding && <Card className="p-4"><TemplateForm onDone={() => { setAdding(false); load() }} onCancel={() => setAdding(false)} /></Card>}
      {templates.length === 0 && !adding ? (
        <p className="text-sm text-zinc-600">No templates yet — create one to generate recurring shifts.</p>
      ) : (
        <div className="space-y-2">
          {templates.map((t) => <TemplateRow key={t.id} tpl={t} onChanged={load} onGenerated={onGenerated} />)}
        </div>
      )}
    </div>
  )
}

function TemplateRow({ tpl, onChanged, onGenerated }: { tpl: ShiftTemplate; onChanged: () => void; onGenerated: () => void }) {
  const { toast } = useToast()
  const [busy, setBusy] = useState(false)
  const [genOpen, setGenOpen] = useState(false)
  const today = toISODate(new Date())
  const [from, setFrom] = useState(today)
  const [to, setTo] = useState(addDays(today, 13))
  const [genBusy, setGenBusy] = useState(false)

  async function remove() {
    setBusy(true)
    try { await deleteTemplate(tpl.id); onChanged() } finally { setBusy(false) }
  }
  async function generate() {
    setGenBusy(true)
    try {
      const res = await generateFromTemplate(tpl.id, from, to)
      onGenerated()
      const warnings = res.compliance_warnings ?? []
      if (warnings.length) {
        // 'info', not 'error': generation SUCCEEDED — a red toast here reads as
        // failure and invites a retry that duplicates the whole shift series.
        toast(`Generated ${res.created} shift(s) — scheduling-law note: ${warnings.map((w) => w.message).join('; ')}`, 'info')
      }
    } finally { setGenBusy(false) }
  }

  return (
    <Card className="p-3">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="text-sm text-zinc-200">{tpl.name}</div>
          <div className="text-[11px] text-zinc-500">
            {fmtTime(`2000-01-01T${tpl.start_time}Z`)}–{fmtTime(`2000-01-01T${tpl.end_time}Z`)}
            {tpl.role ? ` · ${tpl.role}` : ''} · {tpl.required_staff} staff
            {' · '}{tpl.days_of_week.length ? tpl.days_of_week.map((d) => WEEKDAY_LABELS[d]).join(' ') : 'no days set'}
          </div>
        </div>
        <button onClick={() => setGenOpen((v) => !v)} className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300"><Sparkles className="h-3.5 w-3.5" /> Generate</button>
        <button onClick={remove} disabled={busy} className="text-zinc-600 hover:text-red-400 p-1"><Trash2 className="h-4 w-4" /></button>
      </div>
      {genOpen && (
        <div className="mt-3 flex items-end gap-2 flex-wrap border-t border-zinc-800 pt-3">
          <label className="block"><span className="text-[10px] text-zinc-500 uppercase">From</span><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={`${inputCls} mt-1`} /></label>
          <label className="block"><span className="text-[10px] text-zinc-500 uppercase">To</span><input type="date" value={to} onChange={(e) => setTo(e.target.value)} className={`${inputCls} mt-1`} /></label>
          <button onClick={generate} disabled={genBusy || !tpl.days_of_week.length} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-3 py-1.5 disabled:opacity-50">{genBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Generate drafts</button>
        </div>
      )}
    </Card>
  )
}

function TemplateForm({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const [name, setName] = useState('')
  const [role, setRole] = useState('')
  const [start, setStart] = useState('09:00')
  const [end, setEnd] = useState('17:00')
  const [required, setRequired] = useState('1')
  const [days, setDays] = useState<number[]>([1, 2, 3, 4, 5])
  const [busy, setBusy] = useState(false)

  function toggleDay(d: number) {
    setDays((prev) => prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort((a, b) => a - b))
  }
  async function save() {
    if (!name.trim()) return
    setBusy(true)
    try {
      await createTemplate({
        name: name.trim(), role: role.trim() || null,
        start_time: `${start}:00`, end_time: `${end}:00`,
        required_staff: Math.max(1, Math.round(Number(required) || 1)),
        days_of_week: days,
      })
      onDone()
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <label className="block"><span className="text-[10px] text-zinc-500 uppercase">Name</span><input value={name} onChange={(e) => setName(e.target.value)} className={`${inputCls} mt-1`} /></label>
        <label className="block"><span className="text-[10px] text-zinc-500 uppercase">Role</span><input value={role} onChange={(e) => setRole(e.target.value)} className={`${inputCls} mt-1`} /></label>
        <label className="block"><span className="text-[10px] text-zinc-500 uppercase">Start</span><input type="time" value={start} onChange={(e) => setStart(e.target.value)} className={`${inputCls} mt-1`} /></label>
        <label className="block"><span className="text-[10px] text-zinc-500 uppercase">End</span><input type="time" value={end} onChange={(e) => setEnd(e.target.value)} className={`${inputCls} mt-1`} /></label>
      </div>
      <label className="block max-w-[120px]"><span className="text-[10px] text-zinc-500 uppercase">Staff needed</span><input value={required} onChange={(e) => setRequired(e.target.value)} className={`${inputCls} mt-1`} /></label>
      <div>
        <span className="text-[10px] text-zinc-500 uppercase">Repeat on</span>
        <div className="flex gap-1 mt-1">
          {WEEKDAY_LABELS.map((lbl, i) => (
            <button key={i} onClick={() => toggleDay(i)} className={`w-9 py-1 rounded-md text-xs border ${days.includes(i) ? 'bg-emerald-600 border-emerald-500 text-white' : 'border-zinc-700 text-zinc-400 hover:text-zinc-100'}`}>{lbl[0]}</button>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button onClick={save} disabled={busy || !name.trim()} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-3 py-1.5 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Save template</button>
        <button onClick={onCancel} className="text-xs text-zinc-400 hover:text-zinc-100 px-3 py-1.5 rounded-lg border border-zinc-700">Cancel</button>
      </div>
    </div>
  )
}

// ---------- Requests tab ----------

function RequestsTab({ onReviewed }: { onReviewed: () => void }) {
  const { toast } = useToast()
  const [requests, setRequests] = useState<ScheduleRequest[]>([])
  const [loading, setLoading] = useState(true)
  const load = useCallback(() => fetchRequests().then((r) => setRequests(r.requests)), [])
  useEffect(() => { load().finally(() => setLoading(false)) }, [load])

  async function review(id: string, decision: 'approved' | 'denied') {
    try {
      await reviewRequest(id, decision)
    } catch (err) {
      const prompt = conflictPrompt(err)
      if (!prompt) {
        // Includes the 409 another admin causes by reviewing this first, and the
        // 409 for a swap target who has since left. Both must reload: the row on
        // screen is stale, and leaving it there gives the admin live Approve/Deny
        // buttons that appear to do nothing.
        toast(errorMessage(err), 'error')
        await load()
        onReviewed()
        return
      }
      if (!window.confirm(prompt)) return
      try {
        await reviewRequest(id, decision, undefined, true)
      } catch (forcedErr) {
        toast(errorMessage(forcedErr), 'error')
        await load()
        onReviewed()
        return
      }
    }
    await load()
    onReviewed()
  }

  if (loading) return <div className="flex items-center justify-center h-40"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  if (requests.length === 0) return <p className="text-sm text-zinc-600">No schedule requests.</p>

  return (
    <div className="space-y-2">
      {requests.map((r) => (
        <Card key={r.id} className="p-3">
          <div className="flex items-center gap-3 flex-wrap">
            <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase ${REQUEST_TONE[r.status]}`}>{r.status}</span>
            <div className="flex-1 min-w-0">
              <div className="text-sm text-zinc-200">{r.employee_name} · <span className="capitalize">{r.request_type}</span></div>
              <div className="text-[11px] text-zinc-500">
                {r.request_type === 'unavailable'
                  ? `${r.unavailable_start ?? ''} → ${r.unavailable_end ?? ''}`
                  : r.shift_starts_at ? `${fmtDayLabel(r.shift_starts_at.slice(0, 10))} ${fmtTime(r.shift_starts_at)}${r.shift_ends_at ? `–${fmtTime(r.shift_ends_at)}` : ''}` : '—'}
                {r.reason ? ` · “${r.reason}”` : ''}
              </div>
            </div>
            {r.status === 'pending' && (
              <div className="flex items-center gap-1.5">
                <button onClick={() => review(r.id, 'approved')} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs rounded-lg px-2.5 py-1.5"><Check className="h-3.5 w-3.5" /> Approve</button>
                <button onClick={() => review(r.id, 'denied')} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2.5 py-1.5 rounded-lg border border-zinc-700"><X className="h-3.5 w-3.5" /> Deny</button>
              </div>
            )}
          </div>
        </Card>
      ))}
    </div>
  )
}
