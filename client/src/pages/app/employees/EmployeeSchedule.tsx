import { useEffect, useRef, useState, useCallback } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  BarChart2, CalendarDays, Loader2, Plus, Trash2, ChevronLeft, ChevronRight, Check, X,
  Send, Users, LayoutTemplate, Inbox, Sparkles, Pencil, Copy, AlertTriangle, CircleHelp, CalendarClock,
  History,
} from 'lucide-react'
import { Card, useToast } from '../../../components/ui'
import { ApiError } from '../../../api/client'
import {
  createShift, updateShift, deleteShift, publishShift,
  assignEmployee, unassignEmployee, fetchWeekTemplates, createWeekTemplate, replaceWeekTemplate, deleteWeekTemplate,
  generateFromWeekTemplate, fetchRequests, reviewRequest, duplicateShift,
  fetchEligibilityCases, type ScheduleEligibilityCase,
} from '../../../api/employees/employeeSchedule'
import { conflictPrompt } from './scheduleConflicts'
import { trainingApi, type TrainingRequirement } from '../../../api/training/training'
import type {
  Shift, RosterEmployee, WeekTemplate, ScheduleRequest, ShiftPayload, RosterFlags,
} from '../../../types/employeeSchedule'
import {
  STATUS_TONE, REQUEST_TONE, errorMessage,
  fmtTime, fmtDayLabel, toISODate, addDays, startOfWeekSunday,
} from '../../../types/employeeSchedule'
import { useEmployeeSchedule } from './useEmployeeSchedule'
import type { EmployeeScheduleTab } from './useEmployeeSchedule'
import ScheduleIntelligence from './ScheduleIntelligence'
import ScheduleLawPanel from '../../../components/employees/ScheduleLawPanel'
import ScheduleHelperWizard from '../../../components/employees/onboarding/ScheduleHelperWizard'
import { useMe } from '../../../hooks/useMe'
import { useLocationScope } from '../../../hooks/useLocationScope'
import LocationPicker from '../../../components/shared/LocationPicker'
import AutoSchedulesTab from '../../../components/employees/AutoSchedulesTab'
import ScheduleAuditLog from '../../../components/employees/ScheduleAuditLog'
import {
  MAX_BREAK_MINUTES,
  MAX_REQUIRED_STAFF,
  validateShiftFields,
} from '../../../components/employees/schedule-editor/shiftValidation'
import { getScheduleSuggestionStatus, type ScheduleSuggestionStatus } from '../../../api/employees/scheduleAssistant'

const inputCls = 'bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 w-full'
const SCHEDULE_GUIDE_STORAGE_KEY = 'matcha.employee-schedule.guide.v1'

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
  const { me, hasFeature, loading: meLoading } = useMe()
  const { toast } = useToast()
  const { locationId, setLocationId, locations, loading: locationsLoading } = useLocationScope()
  const [guideOpen, setGuideOpen] = useState(() => {
    try { return window.localStorage.getItem(SCHEDULE_GUIDE_STORAGE_KEY) !== 'seen' } catch { return true }
  })
  const [automaticSuggestion, setAutomaticSuggestion] = useState<ScheduleSuggestionStatus | null>(null)
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
  } = useEmployeeSchedule(linkedDate, initialTab, locationId)

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

  useEffect(() => {
    let cancelled = false
    setAutomaticSuggestion(null)
    if (!locationId || tab !== 'schedule') return () => { cancelled = true }
    void getScheduleSuggestionStatus(locationId, weekStart)
      .then((result) => {
        if (!cancelled) setAutomaticSuggestion(result.available ? result : null)
      })
      .catch(() => {
        if (!cancelled) setAutomaticSuggestion(null)
      })
    return () => { cancelled = true }
  }, [locationId, tab, weekStart])

  function setTab(nextTab: EmployeeScheduleTab) {
    setScheduleTab(nextTab)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (nextTab === 'schedule') next.delete('tab')
      else next.set('tab', nextTab)
      return next
    }, { replace: true })
  }

  function closeGuide() {
    try { window.localStorage.setItem(SCHEDULE_GUIDE_STORAGE_KEY, 'seen') } catch { /* best effort */ }
    setGuideOpen(false)
  }

  async function handlePublishWeek() {
    try {
      await publishWeek()
    } catch (err) {
      const detail = err instanceof ApiError
        ? err.body as { detail?: { code?: string } }
        : null
      toast(
        detail?.detail?.code === 'schedule_location_not_ready'
          ? "Complete this location's scheduling prerequisites before publishing."
          : errorMessage(err),
        'error',
      )
    }
  }

  return (
    // Same page frame as Compliance/Dashboard/Onboarding/Company/OSHA Logs.
    // Tab STYLE kept as-is (icon + label, underline) rather than switched to
    // the compact mono tabs those pages use — it's already a deliberate,
    // working motif here, not a chunky-button substitute like Compliance's
    // Button-pills were. Only the shell + tab band placement change.
    <div className="min-w-0 overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
      <div className="border-b border-white/[0.06] px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-light tracking-tight text-zinc-50 flex items-center gap-2">
              <CalendarDays className="h-5 w-5 text-zinc-500" /> Employee Schedule
            </h1>
            <p className="text-sm text-zinc-500 mt-1 max-w-2xl">Build weekly shifts over your roster, assign employees, and publish. Generate recurring weeks from reusable templates. Employees see published shifts and can request swaps or time off.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button onClick={() => setGuideOpen(true)} className="inline-flex items-center gap-1 text-sm text-zinc-300 hover:text-zinc-100 px-3 py-2 rounded-lg border border-zinc-700" aria-label="Open scheduling guide">
              <CircleHelp className="h-4 w-4" /> How scheduling works
            </button>
            <ScheduleLawPanel />
            <Link
              to={`/ops/schedule/editor?week=${weekStart}${locationId ? `&location=${locationId}` : ''}`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 px-3 py-2 text-sm text-emerald-300 hover:border-emerald-400/60 hover:text-emerald-200"
            >
              Full shift editor
            </Link>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 border-b border-white/[0.06] px-5">
        <div className="flex items-center gap-1">
          <TabButton active={tab === 'schedule'} onClick={() => setTab('schedule')} icon={<CalendarDays className="h-4 w-4" />}>Schedule</TabButton>
          <TabButton active={tab === 'templates'} onClick={() => setTab('templates')} icon={<LayoutTemplate className="h-4 w-4" />}>Templates</TabButton>
          <TabButton active={tab === 'auto-schedules'} onClick={() => setTab('auto-schedules')} icon={<CalendarClock className="h-4 w-4" />}>Auto schedules</TabButton>
          <TabButton active={tab === 'requests'} onClick={() => setTab('requests')} icon={<Inbox className="h-4 w-4" />}>Requests</TabButton>
          <TabButton active={tab === 'audit'} onClick={() => setTab('audit')} icon={<History className="h-4 w-4" />}>Audit log</TabButton>
          {intelligenceEnabled && <TabButton active={tab === 'intelligence'} onClick={() => setTab('intelligence')} icon={<BarChart2 className="h-4 w-4" />}>Intelligence</TabButton>}
        </div>
        {tab !== 'audit' && <LocationPicker locations={locations} value={locationId} onChange={setLocationId} />}
      </div>

      <div className="min-w-0 space-y-6 p-5">

      {tab === 'schedule' && (
        <>
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-2">
              <button onClick={() => setWeekStart((w) => addDays(w, -7))} className="text-zinc-400 hover:text-zinc-100 p-1.5 rounded-lg border border-white/[0.08]"><ChevronLeft className="h-4 w-4" /></button>
              <button onClick={() => setWeekStart(toISODate(startOfWeekSunday(new Date())))} className="text-sm text-zinc-300 hover:text-zinc-100 px-3 py-1.5 rounded-lg border border-white/[0.08]">This week</button>
              <button onClick={() => setWeekStart((w) => addDays(w, 7))} className="text-zinc-400 hover:text-zinc-100 p-1.5 rounded-lg border border-white/[0.08]"><ChevronRight className="h-4 w-4" /></button>
              <span className="text-sm text-zinc-500 ml-1">Week of {fmtDayLabel(weekStart)}</span>
            </div>
            <button onClick={handlePublishWeek} disabled={publishing || !summary?.draft || !locationId} className="inline-flex items-center gap-1.5 text-sm text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-2 font-medium disabled:opacity-40">
              {publishing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Publish week{summary?.draft ? ` (${summary.draft})` : ''}
            </button>
          </div>

          {automaticSuggestion?.week_start && locationId && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.07] px-3 py-2 text-xs text-emerald-100">
              <Sparkles className="h-4 w-4 shrink-0 text-emerald-300" />
              <span>Huume prepared a suggested schedule for the week of {automaticSuggestion.week_start}.</span>
              <Link
                to={`/ops/schedule/editor?week=${automaticSuggestion.week_start}&location=${locationId}`}
                className="ml-auto font-medium text-emerald-300 hover:text-emerald-200"
              >
                Review suggestion
              </Link>
            </div>
          )}

          {!locationId && !locationsLoading ? (
            <div className="flex items-center justify-center h-64 text-sm text-zinc-500">Select a location to view its schedule.</div>
          ) : summary && (
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
          ) : !locationId ? null : (
            <div className="min-w-0 overflow-x-auto pb-2">
              <div className="grid min-w-0 grid-cols-1 gap-3 md:min-w-[1260px] md:grid-cols-7">
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
                    locationId={locationId}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {tab === 'templates' && <TemplatesTab locationId={locationId} onGenerated={() => { setTab('schedule'); reload() }} />}
      {tab === 'auto-schedules' && <AutoSchedulesTab locationId={locationId} />}
      {tab === 'requests' && <RequestsTab locationId={locationId} onReviewed={reload} />}
      {tab === 'audit' && <ScheduleAuditLog />}
      {tab === 'intelligence' && intelligenceEnabled && <ScheduleIntelligence />}
      </div>
      <ScheduleHelperWizard open={guideOpen} onClose={closeGuide} />
    </div>
  )
}

function parseScheduleTab(value: string | null): EmployeeScheduleTab {
  if (value === 'templates' || value === 'auto-schedules' || value === 'requests' || value === 'audit' || value === 'intelligence') return value
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

function DayColumn({ day, shifts, roster, rosterFlags, onPatch, onChanged, highlightShiftId, weekDays, locationId }: {
  day: string; shifts: Shift[]; roster: RosterEmployee[]; rosterFlags: RosterFlags | null
  onPatch: (s: Shift) => void; onChanged: () => void; highlightShiftId?: string; weekDays: string[]; locationId: string
}) {
  const [adding, setAdding] = useState(false)
  return (
    <div className="min-w-0">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wide">{fmtDayLabel(day)}</span>
        <button onClick={() => setAdding((v) => !v)} disabled={!locationId} className="text-zinc-500 hover:text-zinc-200 p-0.5 disabled:opacity-40"><Plus className="h-3.5 w-3.5" /></button>
      </div>
      <div className="space-y-2">
        {adding && (
          <Card className="p-2.5">
            <ShiftForm day={day} locationId={locationId} onDone={() => { setAdding(false); onChanged() }} onCancel={() => setAdding(false)} />
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
      className={`min-h-[176px] min-w-0 rounded-lg border p-3 ${shift.status === 'cancelled' ? 'border-red-500/20 bg-red-500/5 opacity-70' : 'border-zinc-800 bg-zinc-900/60'} ${highlighted ? 'ring-2 ring-emerald-500 ring-offset-2 ring-offset-zinc-950' : ''}`}
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
      <div className="mt-1 text-[10px] text-zinc-500">
        Planned break: {shift.break_minutes > 0 ? `${shift.break_minutes} min` : 'none'}
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {shift.assignments.map((a) => {
          const flags = rosterFlags?.[a.employee_id]
          const lapseCount = (flags?.overdue_training ?? 0) + (flags?.lapsed_credentials ?? 0)
          const warningDetails = flags?.warnings ?? []
          const blockingDetails = [
            ...(flags?.blocking_credentials ?? []),
            ...(flags?.credential_expirations ?? [])
              .filter((credential) => credential.expires_at < shift.starts_at.slice(0, 10))
              .map((credential) => `${credential.label} expired ${credential.expires_at} and blocks new scheduling.`),
          ]
          return (
            <span key={a.employee_id} className="inline-flex items-center gap-1 bg-zinc-800 rounded-full pl-2 pr-1 py-0.5 text-[11px] text-zinc-200">
              {a.name}
              {lapseCount > 0 && (
                <span
                  className="inline-flex shrink-0 text-amber-400"
                  title={warningDetails.join('; ') || `${lapseCount} scheduling warning${lapseCount === 1 ? '' : 's'}`}
                  aria-label={warningDetails.join('; ') || `${lapseCount} scheduling warning${lapseCount === 1 ? '' : 's'}`}
                >
                  <AlertTriangle className="h-3 w-3" />
                </span>
              )}
              {blockingDetails.length > 0 && (
                <span className="inline-flex shrink-0 text-red-400" title={blockingDetails.join('; ')} aria-label={blockingDetails.join('; ')}>
                  <AlertTriangle className="h-3 w-3" />
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

      {shift.notes && <p className="mt-2 line-clamp-3 text-[11px] leading-relaxed text-zinc-500">{shift.notes}</p>}

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
            const blockingDetails = [
              ...(flags?.blocking_credentials ?? []),
              ...(flags?.credential_expirations ?? [])
                .filter((credential) => credential.expires_at < shift.starts_at.slice(0, 10))
                .map((credential) => `${credential.label} expired ${credential.expires_at} and blocks new scheduling.`),
            ]
            return (
              <option key={e.id} value={e.id} disabled={blockingDetails.length > 0}>
                {e.name}{e.job_title ? ` — ${e.job_title}` : ''}{blockingDetails.length > 0 ? ' — BLOCKED: credential required' : lapseCount > 0 ? ` — ⚠ ${lapseCount} lapsed` : ''}
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
function spanHours(start: string, end: string): number | null {
  if (!/^\d{2}:\d{2}$/.test(start) || !/^\d{2}:\d{2}$/.test(end)) return null
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
function ShiftForm({ day, shift, locationId, onDone, onSaved, onCancel }: {
  day: string
  shift?: Shift
  locationId?: string
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
  const [notes, setNotes] = useState(shift?.notes ?? '')
  const [breakMinutes, setBreakMinutes] = useState(String(shift?.break_minutes ?? 0))
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
  const durationHours = spanHours(start, end)

  function buildPayload(requiredStaff: number, plannedBreak: number): ShiftPayload {
    const startDay = editing ? shift!.starts_at.slice(0, 10) : day
    const endDay = overnight ? addDays(startDay, 1) : startDay
    const payload: ShiftPayload = {
      starts_at: `${startDay}T${start}:00Z`,
      ends_at: `${endDay}T${end}:00Z`,
      role: role.trim() || null,
      notes: notes.trim() || null,
      break_minutes: plannedBreak,
      required_staff: requiredStaff,
    }
    if (!editing && kind === 'training' && requirementId) {
      payload.kind = 'training'
      payload.training_requirement_id = requirementId
    }
    if (!editing) payload.location_id = locationId
    return payload
  }

  async function save() {
    const validation = validateShiftFields({
      date: editing ? shift!.starts_at.slice(0, 10) : day,
      start,
      end,
      requiredStaff: required,
      breakMinutes,
    })
    if (!validation.valid) {
      toast(validation.error, 'error')
      return
    }
    if (!editing && kind === 'training' && !requirementId) {
      toast('Select a training requirement for this session', 'error')
      return
    }
    setBusy(true)
    try {
      const payload = buildPayload(validation.requiredStaff, validation.breakMinutes)
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
        <input type="time" required value={start} onChange={(e) => setStart(e.target.value)} className={`${inputCls} mt-0.5`} />
      </label>
      <label className="block">
        <span className="text-[10px] text-zinc-500 uppercase tracking-wide">End</span>
        <input type="time" required value={end} onChange={(e) => setEnd(e.target.value)} className={`${inputCls} mt-0.5`} />
      </label>
      <div className="text-[11px] text-zinc-400 font-medium">
        {durationHours === null ? 'Select start and end times' : (
          <>
            {fmtClock(start)}–{fmtClock(end)}
            <span className="text-zinc-600"> · {durationHours}h{overnight ? ' · next day' : ''}</span>
          </>
        )}
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
        <input type="number" min="1" max={MAX_REQUIRED_STAFF} step="1" required value={required} onChange={(e) => setRequired(e.target.value)} className={`${inputCls} mt-0.5`} />
      </label>
      <label className="block">
        <span className="text-[10px] text-zinc-500 uppercase tracking-wide">Planned break (minutes)</span>
        <input type="number" min="0" max={MAX_BREAK_MINUTES} step="5" required value={breakMinutes} onChange={(e) => setBreakMinutes(e.target.value)} className={`${inputCls} mt-0.5`} />
        <span className="mt-1 block text-[10px] leading-4 text-zinc-600">Used by scheduling-law checks when employees are assigned.</span>
      </label>
      <label className="block">
        <span className="text-[10px] text-zinc-500 uppercase tracking-wide">Notes <span className="text-zinc-600 normal-case">(optional)</span></span>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className={`${inputCls} mt-0.5 resize-y`} />
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

function TemplatesTab({ locationId, onGenerated }: { locationId: string; onGenerated: () => void }) {
  const [templates, setTemplates] = useState<WeekTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<WeekTemplate | null>(null)

  const load = useCallback(async () => {
    if (!locationId) {
      setTemplates([])
      return
    }
    const response = await fetchWeekTemplates(locationId)
    setTemplates(response.week_templates)
  }, [locationId])
  useEffect(() => { load().finally(() => setLoading(false)) }, [load])

  function handleDeleted(templateId: string) {
    if (editing?.id === templateId) {
      setAdding(false)
      setEditing(null)
    }
    void load()
  }

  if (!locationId) return <p className="text-sm text-zinc-600">Select a location to manage its week templates.</p>
  if (loading) return <div className="flex items-center justify-center h-40"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-zinc-200">Shift templates</h3>
        <button onClick={() => { setEditing(null); setAdding(true) }} className="inline-flex items-center gap-1 text-sm text-zinc-300 hover:text-zinc-100 px-3 py-1.5 rounded-lg border border-zinc-700"><Plus className="h-4 w-4" /> New template</button>
      </div>
      {adding && <Card className="p-4"><TemplateForm key={editing?.id ?? 'new'} locationId={locationId} template={editing ?? undefined} onDone={() => { setAdding(false); setEditing(null); load() }} onCancel={() => { setAdding(false); setEditing(null) }} /></Card>}
      {templates.length === 0 && !adding ? (
        <p className="text-sm text-zinc-600">No templates yet — create one to generate recurring shifts.</p>
      ) : (
        <div className="space-y-2">
          {templates.map((t) => <TemplateRow key={t.id} tpl={t} onDeleted={() => handleDeleted(t.id)} onGenerated={onGenerated} onEdit={() => { setEditing(t); setAdding(true) }} />)}
        </div>
      )}
    </div>
  )
}

function TemplateRow({ tpl, onDeleted, onGenerated, onEdit }: { tpl: WeekTemplate; onDeleted: () => void; onGenerated: () => void; onEdit: () => void }) {
  const { toast } = useToast()
  const [busy, setBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [genOpen, setGenOpen] = useState(false)
  const today = toISODate(new Date())
  const [from, setFrom] = useState(today)
  const [to, setTo] = useState(addDays(today, 13))
  const [genBusy, setGenBusy] = useState(false)

  async function remove() {
    setBusy(true)
    try {
      const result = await deleteWeekTemplate(tpl.id)
      setConfirmDelete(false)
      onDeleted()
      if (result.paused_auto_schedules) {
        toast(`Paused ${result.paused_auto_schedules} auto schedule${result.paused_auto_schedules === 1 ? '' : 's'} that used this template.`, 'info')
      }
    } catch (err) {
      toast(errorMessage(err), 'error')
    } finally { setBusy(false) }
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
        <div className="flex-1 min-w-0">
          <div className="text-sm text-zinc-200">{tpl.name}</div>
          <div className="text-[11px] text-zinc-500">
            {tpl.blocks.length === 0 ? 'No shift blocks' : tpl.blocks.map((block) => (
              <span key={block.id} className="block">
                {fmtTime(`2000-01-01T${block.start_time}Z`)}–{fmtTime(`2000-01-01T${block.end_time}Z`)}
                {block.role ? ` · ${block.role}` : ''} · {block.required_staff} staff
                {' · '}{block.break_minutes > 0 ? `${block.break_minutes} min break` : 'no break planned'}
                {' · '}{block.days_of_week.length ? block.days_of_week.map((day) => WEEKDAY_LABELS[day]).join(' ') : 'no days set'}
              </span>
            ))}
          </div>
        </div>
        <button onClick={() => setGenOpen((v) => !v)} className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300"><Sparkles className="h-3.5 w-3.5" /> Generate</button>
        <button onClick={onEdit} disabled={busy} aria-label={`Edit ${tpl.name}`} className="text-zinc-500 hover:text-zinc-100 p-1"><Pencil className="h-4 w-4" /></button>
        <button onClick={() => setConfirmDelete(true)} disabled={busy} aria-label={`Delete ${tpl.name}`} className="text-zinc-600 hover:text-red-400 p-1"><Trash2 className="h-4 w-4" /></button>
      </div>
      {confirmDelete && (
        <div role="alertdialog" aria-modal="true" aria-labelledby={`delete-template-${tpl.id}`} className="mt-3 rounded-lg border border-red-900/60 bg-red-950/20 p-3">
          <p id={`delete-template-${tpl.id}`} className="text-sm text-zinc-200">Delete “{tpl.name}”?</p>
          <p className="mt-1 text-xs text-zinc-500">Its shift blocks will be removed. Previously generated shifts will remain. Any auto schedule using this template will be paused.</p>
          <div className="mt-3 flex items-center gap-2">
            <button onClick={() => setConfirmDelete(false)} disabled={busy} className="text-xs text-zinc-300 hover:text-zinc-100 px-2.5 py-1.5 rounded-lg border border-zinc-700">Cancel</button>
            <button onClick={remove} disabled={busy} className="inline-flex items-center gap-1 bg-red-700 hover:bg-red-600 text-white text-xs font-medium rounded-lg px-2.5 py-1.5 disabled:opacity-50">{busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Delete template</button>
          </div>
        </div>
      )}
      {genOpen && (
        <div className="mt-3 flex items-end gap-2 flex-wrap border-t border-zinc-800 pt-3">
          <label className="block"><span className="text-[10px] text-zinc-500 uppercase">From</span><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={`${inputCls} mt-1`} /></label>
          <label className="block"><span className="text-[10px] text-zinc-500 uppercase">To</span><input type="date" value={to} onChange={(e) => setTo(e.target.value)} className={`${inputCls} mt-1`} /></label>
          <button onClick={generate} disabled={genBusy || !tpl.blocks.some((block) => block.days_of_week.length)} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-3 py-1.5 disabled:opacity-50">{genBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Generate drafts</button>
        </div>
      )}
    </Card>
  )
}

type TemplateBlockDraft = {
  id: number | string
  name: string
  role: string
  start: string
  end: string
  breakMinutes: string
  required: string
  days: number[]
}

const MAX_TEMPLATE_BLOCKS = 40

function newTemplateBlock(id: number): TemplateBlockDraft {
  return {
    id,
    name: '',
    role: '',
    start: '09:00',
    end: '17:00',
    breakMinutes: '0',
    required: '1',
    days: [1, 2, 3, 4, 5],
  }
}

function TemplateForm({ locationId, template, onDone, onCancel }: { locationId: string; template?: WeekTemplate; onDone: () => void; onCancel: () => void }) {
  const [name, setName] = useState(() => template?.name ?? '')
  const [blocks, setBlocks] = useState<TemplateBlockDraft[]>(() => template
    ? template.blocks.map((block) => ({
      id: block.id,
      name: block.name,
      role: block.role ?? '',
      start: block.start_time.slice(0, 5),
      end: block.end_time.slice(0, 5),
      breakMinutes: String(block.break_minutes),
      required: String(block.required_staff),
      days: block.days_of_week,
    }))
    : [newTemplateBlock(1)])
  const [busy, setBusy] = useState(false)
  const blocksValid = blocks.every((block) => block.days.length > 0)

  function updateBlock(id: number | string, patch: Partial<TemplateBlockDraft>) {
    setBlocks((current) => current.map((block) => block.id === id ? { ...block, ...patch } : block))
  }

  function toggleDay(id: number | string, day: number) {
    const block = blocks.find((item) => item.id === id)
    if (!block) return
    updateBlock(id, {
      days: block.days.includes(day)
        ? block.days.filter((item) => item !== day)
        : [...block.days, day].sort((a, b) => a - b),
    })
  }

  function addBlock() {
    setBlocks((current) => {
      if (current.length >= MAX_TEMPLATE_BLOCKS) return current
      const nextId = Math.max(0, ...current.map((block) => typeof block.id === 'number' ? block.id : 0)) + 1
      return [...current, newTemplateBlock(nextId)]
    })
  }

  async function save() {
    if (!name.trim() || blocks.length === 0 || !blocksValid) return
    setBusy(true)
    try {
      const blockPayload = (block: TemplateBlockDraft, index: number) => ({
        id: typeof block.id === 'string' ? block.id : undefined,
        name: block.name.trim() || block.role.trim() || `Shift ${index + 1}`,
        role: block.role.trim() || null,
        start_time: `${block.start}:00`, end_time: `${block.end}:00`,
        break_minutes: Math.max(0, Math.round(Number(block.breakMinutes) || 0)),
        required_staff: Math.max(1, Math.round(Number(block.required) || 1)),
        days_of_week: block.days,
      })
      if (!template) {
        await createWeekTemplate({
          name: name.trim(), location_id: locationId,
          blocks: blocks.map((block, index) => {
            const { id: _id, ...payload } = blockPayload(block, index)
            return payload
          }),
        })
      } else {
        await replaceWeekTemplate(template.id, { name: name.trim(), blocks: blocks.map(blockPayload) })
      }
      onDone()
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-4">
      <label className="block max-w-md"><span className="text-[10px] text-zinc-500 uppercase">Template name</span><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Standard operating week" className={`${inputCls} mt-1`} /></label>
      <div className="space-y-3">
        {blocks.map((block, index) => (
          <div key={block.id} className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-zinc-300">Shift {index + 1}</span>
              {blocks.length > 1 && <button type="button" onClick={() => setBlocks((current) => current.filter((item) => item.id !== block.id))} className="text-xs text-zinc-500 hover:text-red-400">Remove shift</button>}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <label className="block"><span className="text-[10px] text-zinc-500 uppercase">Role</span><input value={block.role} onChange={(e) => updateBlock(block.id, { role: e.target.value })} className={`${inputCls} mt-1`} /></label>
              <label className="block"><span className="text-[10px] text-zinc-500 uppercase">Start</span><input type="time" value={block.start} onChange={(e) => updateBlock(block.id, { start: e.target.value })} className={`${inputCls} mt-1`} /></label>
              <label className="block"><span className="text-[10px] text-zinc-500 uppercase">End</span><input type="time" value={block.end} onChange={(e) => updateBlock(block.id, { end: e.target.value })} className={`${inputCls} mt-1`} /></label>
              <label className="block"><span className="text-[10px] text-zinc-500 uppercase">Staff needed</span><input value={block.required} onChange={(e) => updateBlock(block.id, { required: e.target.value })} className={`${inputCls} mt-1`} /></label>
            </div>
            <div className="grid max-w-sm grid-cols-2 gap-2">
              <label className="block"><span className="text-[10px] text-zinc-500 uppercase">Planned break (minutes)</span><input type="number" min="0" step="5" value={block.breakMinutes} onChange={(e) => updateBlock(block.id, { breakMinutes: e.target.value })} className={`${inputCls} mt-1`} /></label>
            </div>
            <div>
              <span className="text-[10px] text-zinc-500 uppercase">Repeat on</span>
              <div className="flex gap-1 mt-1">
                {WEEKDAY_LABELS.map((lbl, day) => (
                  <button type="button" key={day} aria-label={`${lbl} for shift ${index + 1}`} aria-pressed={block.days.includes(day)} onClick={() => toggleDay(block.id, day)} className={`w-9 py-1 rounded-md text-xs border ${block.days.includes(day) ? 'bg-emerald-600 border-emerald-500 text-white' : 'border-zinc-700 text-zinc-400 hover:text-zinc-100'}`}>{lbl[0]}</button>
                ))}
              </div>
              {block.days.length === 0 && <div className="mt-1 text-xs text-red-400">Select at least one day for this shift.</div>}
            </div>
          </div>
        ))}
        <button type="button" onClick={addBlock} disabled={blocks.length >= MAX_TEMPLATE_BLOCKS} className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 disabled:cursor-not-allowed disabled:text-zinc-600"><Plus className="h-3.5 w-3.5" /> Add shift</button>
        {blocks.length >= MAX_TEMPLATE_BLOCKS && <div className="text-xs text-zinc-500">Maximum 40 shifts per template.</div>}
      </div>
      <div className="flex items-center gap-2">
        <button onClick={save} disabled={busy || !name.trim() || blocks.length === 0 || !blocksValid} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-3 py-1.5 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} {template ? 'Save changes' : 'Save template'}</button>
        <button onClick={onCancel} className="text-xs text-zinc-400 hover:text-zinc-100 px-3 py-1.5 rounded-lg border border-zinc-700">Cancel</button>
      </div>
    </div>
  )
}

// ---------- Requests tab ----------

function RequestsTab({ locationId, onReviewed }: { locationId: string | null; onReviewed: () => void }) {
  const { toast } = useToast()
  const [requests, setRequests] = useState<ScheduleRequest[]>([])
  const [eligibilityCases, setEligibilityCases] = useState<ScheduleEligibilityCase[]>([])
  const [loading, setLoading] = useState(true)
  const load = useCallback(async () => {
    const [requestResult, eligibilityResult] = await Promise.all([
      // A location manager is permitted to see eligibility cases but not the
      // company-wide employee-request inbox.  Do not let that expected 403
      // hide the credential queue from the manager who must act on it.
      fetchRequests().catch((error) => {
        if (error instanceof ApiError && error.status === 403) return { requests: [] }
        throw error
      }),
      fetchEligibilityCases(locationId),
    ])
    setRequests(requestResult.requests)
    setEligibilityCases(eligibilityResult.cases.filter((item) => item.status === 'warning_open' || item.status === 'removal_requested'))
  }, [locationId])
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
  if (requests.length === 0 && eligibilityCases.length === 0) return <p className="text-sm text-zinc-600">No schedule requests or credential alerts.</p>

  return (
    <div className="space-y-2">
      {eligibilityCases.length > 0 && (
        <section className="space-y-2 pb-3 border-b border-zinc-800">
          <div className="text-xs font-medium uppercase tracking-wide text-amber-300">Credential & eligibility</div>
          {eligibilityCases.map((item) => {
            const employeeName = `${item.first_name} ${item.last_name}`.trim() || 'Employee'
            const expiry = item.expires_at ? `expired ${item.expires_at}` : 'requires attention'
            const removed = item.removed_assignment_count > 0
            return (
              <Card key={item.id} className="border-amber-500/30 bg-amber-500/5 p-3">
                <div className="flex items-start gap-3 flex-wrap">
                  <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-amber-300" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-zinc-100">{employeeName} · {item.credential_label || 'Required credential'}</div>
                    <div className="mt-0.5 text-[11px] text-zinc-400">
                      {item.status === 'warning_open'
                        ? `Expires ${item.expires_at ?? 'soon'} — renew before it blocks scheduling.`
                        : item.automatic_enforcement
                          ? `${expiry}. ${removed ? `${item.removed_assignment_count} future shift${item.removed_assignment_count === 1 ? '' : 's'} removed automatically.` : 'New assignments are blocked until renewal.'}`
                          : `${expiry}. ${item.affected_assignment_count} future shift${item.affected_assignment_count === 1 ? '' : 's'} need manager review.`}
                    </div>
                  </div>
                  <Link to={`/app/employees/${item.employee_id}`} className="text-xs text-amber-300 hover:text-amber-200">Open credentials</Link>
                </div>
              </Card>
            )
          })}
        </section>
      )}
      {requests.length > 0 && <div className="text-xs font-medium uppercase tracking-wide text-zinc-500 pt-1">Employee requests</div>}
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
            {r.status === 'awaiting_manager' && (
              <div className="flex items-center gap-1.5">
                {r.counterparty_confirmed_at && <span className="text-xs text-sky-300">Both employees confirmed.</span>}
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
