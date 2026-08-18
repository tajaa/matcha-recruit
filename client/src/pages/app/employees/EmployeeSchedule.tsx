import { useEffect, useRef, useState, useCallback } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  BarChart2, CalendarDays, Loader2, Plus, Trash2, ChevronLeft, ChevronRight, ChevronDown, ChevronUp, Check, X,
  Send, Users, LayoutTemplate, Inbox, Sparkles, Pencil, Copy,
} from 'lucide-react'
import { Card, useToast } from '../../../components/ui'
import {
  createShift, updateShift, deleteShift, publishShift,
  assignEmployee, unassignEmployee, fetchShift,
  fetchWeekTemplates, createWeekTemplate, deleteWeekTemplate,
  addTemplateBlock, updateTemplateBlock, deleteTemplateBlock, generateFromWeekTemplate,
  fetchRequests, reviewRequest, duplicateShift,
} from '../../../api/employees/employeeSchedule'
import { conflictPrompt } from './scheduleConflicts'
import { trainingApi, type TrainingRequirement } from '../../../api/training/training'
import type {
  Shift, RosterEmployee, WeekTemplate, TemplateBlock, BlockPayload, ScheduleRequest, ShiftPayload, RosterFlags,
} from '../../../types/employeeSchedule'
import {
  STATUS_TONE, REQUEST_TONE, errorMessage,
  fmtTime, fmtDayLabel, toISODate, addDays, startOfWeekSunday,
} from '../../../types/employeeSchedule'
import { useEmployeeSchedule } from './useEmployeeSchedule'
import type { EmployeeScheduleTab } from './useEmployeeSchedule'
import ScheduleIntelligence from './ScheduleIntelligence'
import ScheduleLawPanel from '../../../components/employees/ScheduleLawPanel'
import LocationPicker from '../../../components/shared/LocationPicker'
import { useLocationScope } from '../../../hooks/useLocationScope'
import { useMe } from '../../../hooks/useMe'

const inputCls = 'bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 w-full'

const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

export default function EmployeeSchedule() {
  // Deep link from a Huume shift-chat confirmation pill (see
  // work/pages/ChannelView/systemContent.tsx's `[[shift:<id>:<date>]]`
  // token) — ?date= opens the right week, ?shift= highlights + scrolls to
  // the specific shift once it's on screen.
  const [searchParams, setSearchParams] = useSearchParams()
  const linkedDate = searchParams.get('date') ?? undefined
  const highlightShiftId = searchParams.get('shift') ?? undefined
  const requestedTab = parseScheduleTab(searchParams.get('tab'))
  const { locationId, setLocationId, locations } = useLocationScope()
  const { me, hasFeature, loading: meLoading } = useMe()
  const intelligenceEnabled = me?.user.role === 'admin' || hasFeature('schedule_intelligence')
  const initialTab = requestedTab === 'intelligence' && !meLoading && !intelligenceEnabled
    ? 'schedule'
    : requestedTab

  const {
    tab, setTab: setScheduleTab,
    weekStart, setWeekStart,
    shifts,
    roster,
    rosterFlags,
    summary,
    loading,
    publishing,
    reload,
    patchShift,
    publishWeek,
    days,
  } = useEmployeeSchedule(locationId, linkedDate, initialTab)

  // A Huume shift pill (work/pages/ChannelView/systemContent.tsx's
  // `[[shift:<id>:<date>]]` token) links here with ?shift=&date= but no
  // ?location= — the token predates location scoping. Resolve the shift's
  // own location once so the pill still lands somewhere useful.
  useEffect(() => {
    if (locationId || !highlightShiftId) return
    let cancelled = false
    fetchShift(highlightShiftId)
      .then((s) => { if (!cancelled && s.location_id) setLocationId(s.location_id) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [locationId, highlightShiftId, setLocationId])

  useEffect(() => {
    const blockedIntelligence = requestedTab === 'intelligence' && !meLoading && !intelligenceEnabled
    const nextTab = blockedIntelligence ? 'schedule' : requestedTab
    if (tab !== nextTab) setScheduleTab(nextTab)
    if (blockedIntelligence) {
      setSearchParams((current) => {
        const next = new URLSearchParams(current)
        next.delete('tab')
        return next
      }, { replace: true })
    }
  }, [intelligenceEnabled, meLoading, requestedTab, setScheduleTab, setSearchParams, tab])

  function setTab(nextTab: EmployeeScheduleTab) {
    setScheduleTab(nextTab)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (nextTab === 'schedule') next.delete('tab')
      else next.set('tab', nextTab)
      return next
    }, { replace: true })
  }

  return (
    // Same page frame as Compliance/Dashboard/Onboarding/Company/OSHA Logs.
    // Tab STYLE kept as-is (icon + label, underline) rather than switched to
    // the compact mono tabs those pages use — it's already a deliberate,
    // working motif here, not a chunky-button substitute like Compliance's
    // Button-pills were. Only the shell + tab band placement change.
    <div className="min-w-0 overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
      <div className="border-b border-white/[0.06] px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-light tracking-tight text-zinc-50 flex items-center gap-2">
              <CalendarDays className="h-5 w-5 text-zinc-500" /> Employee Schedule
            </h1>
            <p className="text-sm text-zinc-500 mt-1 max-w-2xl">Build weekly shifts over your roster, assign employees, and publish. Generate recurring weeks from reusable templates. Employees see published shifts and can request swaps or time off.</p>
          </div>
           <div className="flex shrink-0 items-center gap-2">
             <LocationPicker locations={locations} value={locationId} onChange={setLocationId} />
             <Link to={`/ops/schedule/editor?week=${weekStart}${locationId ? `&location=${locationId}` : ''}`} className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 px-3 py-2 text-sm text-emerald-300 hover:border-emerald-400/60 hover:text-emerald-200">Full shift editor</Link>
             <ScheduleLawPanel />
           </div>
        </div>
      </div>

      <div className="flex items-center gap-1 border-b border-white/[0.06] px-5">
        <TabButton active={tab === 'schedule'} onClick={() => setTab('schedule')} icon={<CalendarDays className="h-4 w-4" />}>Schedule</TabButton>
        <TabButton active={tab === 'templates'} onClick={() => setTab('templates')} icon={<LayoutTemplate className="h-4 w-4" />}>Templates</TabButton>
        <TabButton active={tab === 'requests'} onClick={() => setTab('requests')} icon={<Inbox className="h-4 w-4" />}>Requests</TabButton>
        {intelligenceEnabled && <TabButton active={tab === 'intelligence'} onClick={() => setTab('intelligence')} icon={<BarChart2 className="h-4 w-4" />}>Intelligence</TabButton>}
      </div>

      <div className="min-w-0 space-y-6 p-5">

      {tab === 'schedule' && (locationId ? (
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
            <div className="min-w-0 overflow-x-auto pb-2">
              <div className="grid min-w-0 grid-cols-1 gap-3 md:min-w-[1120px] md:grid-cols-7">
                {days.map((day) => (
                  <DayColumn
                    key={day}
                    day={day}
                    shifts={shifts.filter((s) => s.starts_at.slice(0, 10) === day)}
                    roster={roster}
                    rosterFlags={rosterFlags}
                    onPatch={patchShift}
                    onChanged={reload}
                    highlightShiftId={highlightShiftId}
                    weekDays={days}
                    defaultLocationId={locationId}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      ) : <PickLocationEmpty hasLocations={locations.length > 0} />)}

      {tab === 'templates' && (locationId
        ? <TemplatesTab locationId={locationId} onGenerated={() => { setTab('schedule'); reload() }} />
        : <PickLocationEmpty hasLocations={locations.length > 0} />)}
      {tab === 'requests' && <RequestsTab onReviewed={reload} />}
      {tab === 'intelligence' && intelligenceEnabled && <ScheduleIntelligence />}
      </div>
    </div>
  )
}

function PickLocationEmpty({ hasLocations }: { hasLocations: boolean }) {
  return (
    <div className="flex min-h-[300px] flex-col items-center justify-center gap-2 text-center">
      <p className="text-sm text-zinc-400">Select a location above to view its schedule.</p>
      {!hasLocations && <p className="text-xs text-zinc-600">No locations set up yet — add one under Company.</p>}
    </div>
  )
}

function parseScheduleTab(value: string | null): EmployeeScheduleTab {
  if (value === 'templates' || value === 'requests' || value === 'intelligence') return value
  return 'schedule'
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
    <div className="min-w-0 bg-zinc-900 px-4 py-4">
      <div className="truncate text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{label}</div>
      <div className={`text-2xl font-light font-mono mt-1.5 ${tone}`}>{value}</div>
    </div>
  )
}

function DayColumn({ day, shifts, roster, rosterFlags, onPatch, onChanged, highlightShiftId, weekDays, defaultLocationId }: {
  day: string; shifts: Shift[]; roster: RosterEmployee[]; rosterFlags: RosterFlags | null
  onPatch: (s: Shift) => void; onChanged: () => void; highlightShiftId?: string; weekDays: string[]; defaultLocationId?: string
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
            <ShiftForm day={day} defaultLocationId={defaultLocationId} onDone={() => { setAdding(false); onChanged() }} onCancel={() => setAdding(false)} />
          </Card>
        )}
        {shifts.length === 0 && !adding && <p className="text-[11px] text-zinc-700 py-2">No shifts</p>}
        {shifts.map((s) => (
          <ShiftCard
            key={s.id} shift={s} roster={roster} rosterFlags={rosterFlags}
            onPatch={onPatch} onChanged={onChanged}
            highlighted={s.id === highlightShiftId}
            weekDays={weekDays}
          />
        ))}
      </div>
    </div>
  )
}

function ShiftCard({ shift, roster, rosterFlags, onPatch, onChanged, highlighted, weekDays }: {
  shift: Shift; roster: RosterEmployee[]; rosterFlags: RosterFlags | null
  onPatch: (s: Shift) => void; onChanged: () => void; highlighted?: boolean; weekDays: string[]
}) {
  const { toast } = useToast()
  const [busy, setBusy] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [copyOpen, setCopyOpen] = useState(false)
  const [copyDays, setCopyDays] = useState<Set<string>>(new Set())
  const [copyAssignments, setCopyAssignments] = useState(true)
  const cardRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (highlighted) cardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [highlighted])
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
  async function removeAssignment(employeeId: string) {
    setBusy(true)
    try {
      onPatch(await unassignEmployee(shift.id, employeeId))
    } catch (err) {
      const prompt = conflictPrompt(err)
      if (!prompt) {
        toast(errorMessage(err), 'error')
      } else if (window.confirm(prompt)) {
        try {
          onPatch(await unassignEmployee(shift.id, employeeId, true))
        } catch (forcedErr) {
          toast(errorMessage(forcedErr), 'error')
        }
      }
    } finally { setBusy(false) }
  }
  async function remove() {
    setBusy(true)
    try {
      await deleteShift(shift.id)
      onChanged()
    } catch (err) {
      const prompt = conflictPrompt(err)
      if (!prompt) {
        toast(errorMessage(err), 'error')
      } else if (window.confirm(prompt)) {
        try {
          await deleteShift(shift.id, true)
          onChanged()
        } catch (forcedErr) {
          toast(errorMessage(forcedErr), 'error')
        }
      }
    } finally { setBusy(false) }
  }
  async function duplicate() {
    setBusy(true)
    try {
      const res = await duplicateShift(shift.id, [...copyDays], copyAssignments)
      toast(`Copied to ${res.created} day${res.created === 1 ? '' : 's'}`, 'success')
      if (res.dropped.length) {
        // Toast renders in a plain <span> — '\n' would collapse, so join inline.
        toast(res.dropped.map((d) => `${d.name || 'Assignee'} skipped ${d.date}: ${d.reason}`).join('; '), 'info')
      }
      setCopyOpen(false)
      setCopyDays(new Set())
      onChanged()
    } catch (err) {
      toast(errorMessage(err), 'error')
    } finally { setBusy(false) }
  }

  if (editing) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2.5">
        <ShiftForm
          day={shift.starts_at.slice(0, 10)}
          shift={shift}
          onSaved={(s) => { onPatch(s); setEditing(false) }}
          onCancel={() => setEditing(false)}
        />
      </div>
    )
  }

  return (
    <div
      ref={cardRef}
      className={`min-w-0 rounded-lg border p-2.5 ${shift.status === 'cancelled' ? 'border-red-500/20 bg-red-500/5 opacity-70' : 'border-zinc-800 bg-zinc-900/60'} ${highlighted ? 'ring-2 ring-emerald-500 ring-offset-2 ring-offset-zinc-950' : ''}`}
    >
      <div className="flex items-center justify-between gap-1">
        <span className="text-sm font-medium text-zinc-100">{fmtTime(shift.starts_at)}–{fmtTime(shift.ends_at)}</span>
        <span className="flex items-center gap-1">
          {shift.kind === 'training' && (
            <span className="px-1.5 py-0.5 rounded-full border text-[9px] font-semibold uppercase text-sky-400 bg-sky-500/10 border-sky-500/20">Training</span>
          )}
          <span className={`px-1.5 py-0.5 rounded-full border text-[9px] font-semibold uppercase ${STATUS_TONE[shift.status]}`}>{shift.status}</span>
        </span>
      </div>
      {(shift.role || shift.department) && (
        <div className="text-[11px] text-zinc-400 mt-0.5 truncate">{[shift.role, shift.department].filter(Boolean).join(' · ')}</div>
      )}
      <div className="mt-2 flex flex-wrap gap-1">
        {shift.assignments.map((a) => {
          const flags = rosterFlags?.[a.employee_id]
          const lapseCount = (flags?.overdue_training ?? 0) + (flags?.lapsed_credentials ?? 0)
          return (
            <span key={a.employee_id} className="inline-flex items-center gap-1 bg-zinc-800 rounded-full pl-2 pr-1 py-0.5 text-[11px] text-zinc-200">
              {a.name}
              {a.availability_overridden && (
                <span className="text-orange-400" title="Availability override">Availability override</span>
              )}
              {lapseCount > 0 && (
                <span className="text-amber-400" title={`${flags?.overdue_training ?? 0} overdue training, ${flags?.lapsed_credentials ?? 0} lapsed credential(s)`}>
                  ⚠ {lapseCount}
                </span>
              )}
              <button onClick={() => removeAssignment(a.employee_id)} disabled={busy} className="text-zinc-500 hover:text-red-400"><X className="h-3 w-3" /></button>
            </span>
          )
        })}
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
          {available.map((e) => {
            const flags = rosterFlags?.[e.id]
            const lapseCount = (flags?.overdue_training ?? 0) + (flags?.lapsed_credentials ?? 0)
            return (
              <option key={e.id} value={e.id}>
                {e.name}{e.job_title ? ` — ${e.job_title}` : ''}{lapseCount > 0 ? ` — ⚠ ${lapseCount} lapsed` : ''}
              </option>
            )
          })}
        </select>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
        <button onClick={() => setPickerOpen((v) => !v)} disabled={busy || available.length === 0} className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-100 disabled:opacity-40"><Users className="h-3 w-3" /> Assign</button>
        {/* Cancelled is terminal — the backend refuses to republish it, so offering
            an edit here would be a form whose save can only fail. */}
        {shift.status !== 'cancelled' && (
          <button onClick={() => { setPickerOpen(false); setEditing(true) }} disabled={busy} className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-100 disabled:opacity-40"><Pencil className="h-3 w-3" /> Edit</button>
        )}
        {shift.status !== 'cancelled' && (
          <button onClick={() => { setPickerOpen(false); setCopyOpen((v) => !v) }} disabled={busy} className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-100 disabled:opacity-40"><Copy className="h-3 w-3" /> Copy</button>
        )}
        {shift.status === 'draft' && (
          <button onClick={() => act(() => publishShift(shift.id))} disabled={busy} className="inline-flex items-center gap-1 text-[11px] text-emerald-400 hover:text-emerald-300"><Send className="h-3 w-3" /> Publish</button>
        )}
        <button onClick={remove} disabled={busy} className="inline-flex items-center gap-1 text-[11px] text-zinc-600 hover:text-red-400 ml-auto"><Trash2 className="h-3 w-3" /></button>
      </div>

      {copyOpen && (
        <div className="mt-2 border-t border-zinc-800 pt-2 space-y-2">
          <div className="flex gap-1">
            {weekDays.map((d) => {
              const wd = new Date(`${d}T00:00:00Z`).getUTCDay()
              const isSource = d === shift.starts_at.slice(0, 10)
              const selected = copyDays.has(d)
              return (
                <button
                  key={d}
                  disabled={isSource}
                  onClick={() => setCopyDays((prev) => {
                    const next = new Set(prev)
                    if (next.has(d)) next.delete(d); else next.add(d)
                    return next
                  })}
                  className={`w-8 py-1 rounded-md text-[10px] border ${
                    isSource ? 'opacity-30 border-zinc-800 text-zinc-600'
                      : selected ? 'bg-emerald-600 border-emerald-500 text-white'
                      : 'border-zinc-700 text-zinc-400 hover:text-zinc-100'
                  }`}
                >
                  {WEEKDAY_LABELS[wd][0]}
                </button>
              )
            })}
          </div>
          <label className="flex items-center gap-1.5 text-[11px] text-zinc-400">
            <input type="checkbox" checked={copyAssignments} onChange={(e) => setCopyAssignments(e.target.checked)} />
            Copy assignments
          </label>
          <button
            onClick={duplicate} disabled={busy || copyDays.size === 0}
            className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs rounded-lg px-2.5 py-1.5 disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Copy className="h-3.5 w-3.5" />} Copy to {copyDays.size || ''} day{copyDays.size === 1 ? '' : 's'}
          </button>
        </div>
      )}
    </div>
  )
}

/** "HH:MM" → the same wall-clock time formatted like every other time on this
 *  page. Shifts are stored and rendered as UTC wall-clock throughout (see
 *  fmtTime), so the 2000-01-01 stub is a formatting vehicle, not a date. */
function fmtClock(hhmm: string): string {
  return /^\d{2}:\d{2}$/.test(hhmm) ? fmtTime(`2000-01-01T${hhmm}:00Z`) : '—'
}

/** Length of the window in hours, wrapping past midnight the same way save() does. */
function spanHours(start: string, end: string): number {
  const [sh, sm] = start.split(':').map(Number)
  const [eh, em] = end.split(':').map(Number)
  const mins = (eh * 60 + em) - (sh * 60 + sm)
  return Math.round(((mins <= 0 ? mins + 1440 : mins) / 60) * 10) / 10
}

/** Create (no `shift`) or edit (with `shift`) one shift.
 *
 *  Times are stacked full-width rather than side-by-side: in the 7-column day
 *  grid a half-width native time input collapses to just its picker icon, so the
 *  chosen time was invisible until the card re-rendered post-submit. The preview
 *  line below is the belt to that braces — the selection is legible even where
 *  the native control isn't. */
function ShiftForm({ day, shift, defaultLocationId, onDone, onSaved, onCancel }: {
  day: string
  shift?: Shift
  defaultLocationId?: string
  onDone?: () => void
  onSaved?: (s: Shift) => void
  onCancel: () => void
}) {
  const { toast } = useToast()
  const { hasFeature } = useMe()
  const trainingEnabled = hasFeature('training')
  const editing = !!shift
  const [start, setStart] = useState(shift ? shift.starts_at.slice(11, 16) : '09:00')
  const [end, setEnd] = useState(shift ? shift.ends_at.slice(11, 16) : '17:00')
  const [role, setRole] = useState(shift?.role ?? '')
  const [required, setRequired] = useState(String(shift?.required_staff ?? 1))
  const [busy, setBusy] = useState(false)

  // Training-as-shift: kind is immutable after create (no field on
  // ShiftUpdate), so the toggle only renders for a brand-new shift.
  const [kind, setKind] = useState<'work' | 'training'>('work')
  const [requirementId, setRequirementId] = useState('')
  const [requirements, setRequirements] = useState<TrainingRequirement[]>([])
  useEffect(() => {
    if (editing || !trainingEnabled) return
    trainingApi.listRequirements().then(setRequirements).catch(() => setRequirements([]))
  }, [editing, trainingEnabled])

  const overnight = end <= start

  function buildPayload(): ShiftPayload {
    const startDay = editing ? shift!.starts_at.slice(0, 10) : day
    const endDay = overnight ? addDays(startDay, 1) : startDay
    const payload: ShiftPayload = {
      starts_at: `${startDay}T${start}:00Z`,
      ends_at: `${endDay}T${end}:00Z`,
      role: role.trim() || null,
      required_staff: Math.max(1, Math.round(Number(required) || 1)),
    }
    if (!editing && defaultLocationId) {
      payload.location_id = defaultLocationId
    }
    if (!editing && kind === 'training' && requirementId) {
      payload.kind = 'training'
      payload.training_requirement_id = requirementId
    }
    return payload
  }

  async function save() {
    if (!editing && kind === 'training' && !requirementId) {
      toast('Select a training requirement for this session', 'error')
      return
    }
    setBusy(true)
    try {
      const payload = buildPayload()
      if (editing) {
        // PUT is a true PATCH, but every field here is one the form owns, so
        // sending the lot is the same write. `status` is deliberately NOT sent —
        // editing a published shift must not silently unpublish it.
        try {
          onSaved?.(await updateShift(shift!.id, payload))
        } catch (err) {
          // Retiming can double-book an assignee or trip a scheduling-law
          // advisory — same forceable 409s the assign path handles.
          const prompt = conflictPrompt(err)
          if (!prompt) { toast(errorMessage(err), 'error'); return }
          if (!window.confirm(prompt)) return
          onSaved?.(await updateShift(shift!.id, payload, true))
        }
      } else {
        try {
          await createShift(payload)
        } catch (err) {
          // Was swallowed entirely: a 409 left the form open with no feedback,
          // reading as "the button does nothing".
          const prompt = conflictPrompt(err)
          if (!prompt) { toast(errorMessage(err), 'error'); return }
          if (!window.confirm(prompt)) return
          await createShift(payload, true)
        }
        onDone?.()
      }
    } catch (err) {
      toast(errorMessage(err), 'error')
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-1.5">
      <label className="block">
        <span className="text-[10px] text-zinc-500 uppercase tracking-wide">Start</span>
        <input type="time" value={start} onChange={(e) => setStart(e.target.value)} className={`${inputCls} mt-0.5`} />
      </label>
      <label className="block">
        <span className="text-[10px] text-zinc-500 uppercase tracking-wide">End</span>
        <input type="time" value={end} onChange={(e) => setEnd(e.target.value)} className={`${inputCls} mt-0.5`} />
      </label>
      <div className="text-[11px] text-zinc-400 font-medium">
        {fmtClock(start)}–{fmtClock(end)}
        <span className="text-zinc-600"> · {spanHours(start, end)}h{overnight ? ' · next day' : ''}</span>
      </div>
      <label className="block">
        {/* Labelled rather than placeholder-only: "Role (optional)" clips to
            "Role (option…" at day-column width, and a clipped placeholder
            disappears entirely the moment you type. */}
        <span className="text-[10px] text-zinc-500 uppercase tracking-wide">Role <span className="text-zinc-600 normal-case">(optional)</span></span>
        <input value={role} onChange={(e) => setRole(e.target.value)} className={`${inputCls} mt-0.5`} />
      </label>
      <label className="block">
        <span className="text-[10px] text-zinc-500 uppercase tracking-wide">Staff needed</span>
        <input value={required} onChange={(e) => setRequired(e.target.value)} className={`${inputCls} mt-0.5`} />
      </label>
      {!editing && trainingEnabled && (
        <label className="block">
          <span className="text-[10px] text-zinc-500 uppercase tracking-wide">Kind</span>
          <div className="mt-0.5 flex rounded-lg border border-zinc-700 overflow-hidden text-xs">
            <button type="button" onClick={() => setKind('work')} className={`flex-1 px-2 py-1.5 ${kind === 'work' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}>Work</button>
            <button type="button" onClick={() => setKind('training')} className={`flex-1 px-2 py-1.5 ${kind === 'training' ? 'bg-sky-600 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>Training</button>
          </div>
        </label>
      )}
      {!editing && trainingEnabled && kind === 'training' && (
        <label className="block">
          <span className="text-[10px] text-zinc-500 uppercase tracking-wide">Training requirement</span>
          <select value={requirementId} onChange={(e) => setRequirementId(e.target.value)} className={`${inputCls} mt-0.5`}>
            <option value="">Select requirement…</option>
            {requirements.map((r) => <option key={r.id} value={r.id}>{r.title}</option>)}
          </select>
        </label>
      )}
      <div className="flex items-center gap-1.5">
        <button onClick={save} disabled={busy} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-2.5 py-1.5 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} {editing ? 'Save' : 'Add'}</button>
        <button onClick={onCancel} className="text-xs text-zinc-400 hover:text-zinc-100 px-2.5 py-1.5 rounded-lg border border-zinc-700">Cancel</button>
      </div>
    </div>
  )
}

// ---------- Templates tab ----------
//
// A week template is a named container of shift blocks (each block = one
// shift definition, same shape templates used to be flat rows of). Location
// lives on the parent only; a block always inherits it (server-enforced).
// Generation materializes every block's shifts under one series_id, so a
// whole week is produced — and can be re-produced for a similar week — in
// one action instead of one generate call per shift definition.

function TemplatesTab({ locationId, onGenerated }: { locationId: string; onGenerated: () => void }) {
  const [weekTemplates, setWeekTemplates] = useState<WeekTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [creatingNew, setCreatingNew] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetchWeekTemplates(locationId)
      setWeekTemplates(r.week_templates)
    } finally {
      setLoading(false)
    }
  }, [locationId])
  useEffect(() => { void load() }, [load])

  if (loading) return <div className="flex items-center justify-center h-40"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-zinc-200">Week templates</h3>
        <button onClick={() => setCreatingNew((v) => !v)} className="inline-flex items-center gap-1 text-sm text-zinc-300 hover:text-zinc-100 px-3 py-1.5 rounded-lg border border-zinc-700"><Plus className="h-4 w-4" /> New week template</button>
      </div>
      {creatingNew && <Card className="p-4"><WeekTemplateForm defaultLocationId={locationId} onDone={() => { setCreatingNew(false); load() }} onCancel={() => setCreatingNew(false)} /></Card>}
      {weekTemplates.length === 0 && !creatingNew ? (
        <p className="text-sm text-zinc-600">No week templates for this location yet — build one (e.g. "Standard Week") to generate a full week of shifts in one action.</p>
      ) : (
        <div className="space-y-2">
          {weekTemplates.map((t) => <WeekTemplateCard key={t.id} tpl={t} onChanged={load} onGenerated={onGenerated} />)}
        </div>
      )}
    </div>
  )
}

function WeekTemplateCard({ tpl, onChanged, onGenerated }: { tpl: WeekTemplate; onChanged: () => void; onGenerated: () => void }) {
  const { toast } = useToast()
  const [expanded, setExpanded] = useState(false)
  const [addingBlock, setAddingBlock] = useState(false)
  const [busy, setBusy] = useState(false)
  const [genOpen, setGenOpen] = useState(false)
  const today = toISODate(new Date())
  const [from, setFrom] = useState(today)
  const [to, setTo] = useState(addDays(today, 6))
  const [genBusy, setGenBusy] = useState(false)

  const totalShiftsPerRun = tpl.blocks.reduce((n, b) => n + b.days_of_week.length, 0)
  const canGenerate = tpl.blocks.some((b) => b.days_of_week.length > 0)

  async function remove() {
    setBusy(true)
    try { await deleteWeekTemplate(tpl.id); onChanged() } finally { setBusy(false) }
  }
  async function generate() {
    setGenBusy(true)
    try {
      const res = await generateFromWeekTemplate(tpl.id, from, to)
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
        <button onClick={() => setExpanded((v) => !v)} className="text-zinc-500 hover:text-zinc-200 p-0.5">
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
        <div className="flex-1 min-w-0">
          <div className="text-sm text-zinc-200">{tpl.name}</div>
          <div className="text-[11px] text-zinc-500">
            {tpl.blocks.length} block{tpl.blocks.length === 1 ? '' : 's'}
            {' · '}~{totalShiftsPerRun} shift{totalShiftsPerRun === 1 ? '' : 's'} per week
          </div>
        </div>
        <button onClick={() => setGenOpen((v) => !v)} className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300"><Sparkles className="h-3.5 w-3.5" /> Generate</button>
        <button onClick={remove} disabled={busy} className="text-zinc-600 hover:text-red-400 p-1"><Trash2 className="h-4 w-4" /></button>
      </div>
      {genOpen && (
        <div className="mt-3 flex items-end gap-2 flex-wrap border-t border-zinc-800 pt-3">
          <label className="block"><span className="text-[10px] text-zinc-500 uppercase">From</span><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={`${inputCls} mt-1`} /></label>
          <label className="block"><span className="text-[10px] text-zinc-500 uppercase">To</span><input type="date" value={to} onChange={(e) => setTo(e.target.value)} className={`${inputCls} mt-1`} /></label>
          <button onClick={generate} disabled={genBusy || !canGenerate} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-3 py-1.5 disabled:opacity-50">{genBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Generate drafts</button>
        </div>
      )}
      {expanded && (
        <div className="mt-3 space-y-2 border-t border-zinc-800 pt-3">
          {tpl.blocks.length === 0 && !addingBlock && (
            <p className="text-xs text-zinc-600">No blocks yet — add the first shift definition for this week.</p>
          )}
          {tpl.blocks.map((b) => (
            <TemplateBlockRow key={b.id} block={b} weekTemplateId={tpl.id} onChanged={onChanged} />
          ))}
          {addingBlock ? (
            <TemplateBlockForm weekTemplateId={tpl.id} onDone={() => { setAddingBlock(false); onChanged() }} onCancel={() => setAddingBlock(false)} />
          ) : (
            <button onClick={() => setAddingBlock(true)} className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-800"><Plus className="h-3.5 w-3.5" /> Add block</button>
          )}
        </div>
      )}
    </Card>
  )
}

function TemplateBlockRow({ block, weekTemplateId, onChanged }: { block: TemplateBlock; weekTemplateId: string; onChanged: () => void }) {
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)

  async function remove() {
    setBusy(true)
    try { await deleteTemplateBlock(weekTemplateId, block.id); onChanged() } finally { setBusy(false) }
  }

  if (editing) {
    return <TemplateBlockForm weekTemplateId={weekTemplateId} initial={block} onDone={() => { setEditing(false); onChanged() }} onCancel={() => setEditing(false)} />
  }

  return (
    <div className="flex items-center gap-2 rounded-lg border border-zinc-800 px-2.5 py-1.5">
      <div className="flex-1 min-w-0">
        <div className="text-sm text-zinc-200">{block.name}</div>
        <div className="text-[11px] text-zinc-500">
          {fmtTime(`2000-01-01T${block.start_time}Z`)}–{fmtTime(`2000-01-01T${block.end_time}Z`)}
          {block.role ? ` · ${block.role}` : ''} · {block.required_staff} staff
          {' · '}{block.days_of_week.length ? block.days_of_week.map((d) => WEEKDAY_LABELS[d]).join(' ') : 'no days set'}
        </div>
      </div>
      <button onClick={() => setEditing(true)} className="text-zinc-600 hover:text-zinc-200 p-1"><Pencil className="h-3.5 w-3.5" /></button>
      <button onClick={remove} disabled={busy} className="text-zinc-600 hover:text-red-400 p-1"><Trash2 className="h-3.5 w-3.5" /></button>
    </div>
  )
}

function TemplateBlockForm({ weekTemplateId, initial, onStage, onDone, onCancel }: {
  weekTemplateId?: string
  initial?: TemplateBlock
  onStage?: (b: BlockPayload) => void
  onDone?: () => void
  onCancel: () => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [role, setRole] = useState(initial?.role ?? '')
  const [start, setStart] = useState(initial ? initial.start_time.slice(0, 5) : '09:00')
  const [end, setEnd] = useState(initial ? initial.end_time.slice(0, 5) : '17:00')
  const [required, setRequired] = useState(String(initial?.required_staff ?? 1))
  const [days, setDays] = useState<number[]>(initial?.days_of_week ?? [1, 2, 3, 4, 5])
  const [busy, setBusy] = useState(false)

  function toggleDay(d: number) {
    setDays((prev) => prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort((a, b) => a - b))
  }
  async function save() {
    if (!name.trim()) return
    const payload: BlockPayload = {
      name: name.trim(), role: role.trim() || null,
      start_time: `${start}:00`, end_time: `${end}:00`,
      required_staff: Math.max(1, Math.round(Number(required) || 1)),
      days_of_week: days,
    }
    if (onStage) { onStage(payload); return }
    setBusy(true)
    try {
      if (initial) await updateTemplateBlock(weekTemplateId!, initial.id, payload)
      else await addTemplateBlock(weekTemplateId!, payload)
      onDone?.()
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-2 rounded-lg border border-zinc-800 p-3">
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
        <button onClick={save} disabled={busy || !name.trim()} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-3 py-1.5 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} {onStage ? 'Add block' : 'Save block'}</button>
        <button onClick={onCancel} className="text-xs text-zinc-400 hover:text-zinc-100 px-3 py-1.5 rounded-lg border border-zinc-700">Cancel</button>
      </div>
    </div>
  )
}

function WeekTemplateForm({ defaultLocationId, onDone, onCancel }: { defaultLocationId?: string; onDone: () => void; onCancel: () => void }) {
  const [name, setName] = useState('')
  const [notes, setNotes] = useState('')
  const [stagedBlocks, setStagedBlocks] = useState<BlockPayload[]>([])
  const [addingStagedBlock, setAddingStagedBlock] = useState(false)
  const [busy, setBusy] = useState(false)

  async function save() {
    if (!name.trim()) return
    setBusy(true)
    try {
      await createWeekTemplate({
        name: name.trim(), location_id: defaultLocationId || null,
        notes: notes.trim() || null, blocks: stagedBlocks,
      })
      onDone()
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <label className="block"><span className="text-[10px] text-zinc-500 uppercase">Name</span><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Standard Week" className={`${inputCls} mt-1`} /></label>
        <label className="block"><span className="text-[10px] text-zinc-500 uppercase">Notes</span><input value={notes} onChange={(e) => setNotes(e.target.value)} className={`${inputCls} mt-1`} /></label>
      </div>
      {stagedBlocks.length > 0 && (
        <div className="space-y-1.5">
          {stagedBlocks.map((b, i) => (
            <div key={i} className="flex items-center gap-2 rounded-lg border border-zinc-800 px-2.5 py-1.5">
              <div className="flex-1 min-w-0 text-sm text-zinc-200">
                {b.name} <span className="text-[11px] text-zinc-500">
                  {b.start_time?.slice(0, 5)}–{b.end_time?.slice(0, 5)}
                  {b.role ? ` · ${b.role}` : ''} · {b.required_staff} staff
                </span>
              </div>
              <button onClick={() => setStagedBlocks((prev) => prev.filter((_, x) => x !== i))} className="text-zinc-600 hover:text-red-400 p-1"><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
          ))}
        </div>
      )}
      {addingStagedBlock ? (
        <TemplateBlockForm onStage={(b) => { setStagedBlocks((prev) => [...prev, b]); setAddingStagedBlock(false) }} onCancel={() => setAddingStagedBlock(false)} />
      ) : (
        <button onClick={() => setAddingStagedBlock(true)} className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-800"><Plus className="h-3.5 w-3.5" /> Add block</button>
      )}
      <div className="flex items-center gap-2">
        <button onClick={save} disabled={busy || !name.trim()} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-3 py-1.5 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Save week template</button>
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
