import { useEffect, useState, useCallback } from 'react'
import { CalendarClock, Loader2, X, Check, Repeat, LogOut, CalendarOff, AlertTriangle, Clock } from 'lucide-react'
import { useToast } from '../../components/ui'
import {
  fetchMySchedule, fetchMyTeamSchedule, fetchMyRequests, fetchMyOffers, fetchMyCoworkers,
  createMyRequest, cancelMyRequest, acceptMyRequest, withdrawMyRequest,
  fetchMyAvailability, saveMyAvailability, type AvailabilityWindow,
} from '../../api/employees/employeeSchedule'
import type { Shift, ScheduleRequest, ShiftAssignment } from '../../types/employeeSchedule'
import {
  REQUEST_TONE, errorMessage, fmtTime, fmtDayLabel as fmtDay, addDays, toISODate, WEEKDAY_LABELS,
} from '../../types/employeeSchedule'

function todayISO(): string {
  return toISODate(new Date())
}

const inputCls = 'bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 w-full'

export default function PortalSchedule() {
  const { toast } = useToast()
  const [shifts, setShifts] = useState<Shift[]>([])
  const [teamShifts, setTeamShifts] = useState<Shift[]>([])
  const [requests, setRequests] = useState<ScheduleRequest[]>([])
  const [offers, setOffers] = useState<ScheduleRequest[]>([])
  const [coworkers, setCoworkers] = useState<{ id: string; name: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [requestError, setRequestError] = useState<string | null>(null)

  const load = useCallback(async () => {
    const start = todayISO()
    const end = `${addDays(start, 28)}T00:00:00Z`
    const [schedule, teamSchedule, reqs, openOffers, roster] = await Promise.allSettled([
      fetchMySchedule(`${start}T00:00:00Z`, end),
      fetchMyTeamSchedule(`${start}T00:00:00Z`, end),
      fetchMyRequests(),
      fetchMyOffers(),
      fetchMyCoworkers(),
    ])
    if (schedule.status === 'rejected') throw schedule.reason
    setShifts(schedule.value.shifts)
    setLoadError(null)
    const errors: string[] = []
    if (teamSchedule.status === 'fulfilled') setTeamShifts(teamSchedule.value.shifts)
    else errors.push('full schedule')
    if (reqs.status === 'fulfilled') setRequests(reqs.value.requests)
    else errors.push('request history')
    if (openOffers.status === 'fulfilled') setOffers(openOffers.value.offers)
    else errors.push('available offers')
    if (roster.status === 'fulfilled') setCoworkers(roster.value.employees)
    else errors.push('coworkers')
    setRequestError(errors.length ? `Could not load ${errors.join(', ')}. Your published shifts are still available.` : null)
  }, [])

  // Swallowing this would render "no published shifts" — a fake-legitimate empty
  // state — on top of a 403 or a 500.
  useEffect(() => {
    load().catch((err) => setLoadError(errorMessage(err))).finally(() => setLoading(false))
  }, [load])

  const cancelRequest = useCallback(async (id: string) => {
    try {
      await cancelMyRequest(id)
      await load()
    } catch (err) {
      toast(errorMessage(err), 'error')
    }
  }, [load, toast])

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>

  if (loadError) {
    return (
      <div className="max-w-3xl">
        <div className="flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/5 p-4">
          <AlertTriangle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-medium text-zinc-100">Couldn’t load your schedule</div>
            <div className="text-sm text-zinc-400 mt-0.5">{loadError}</div>
          </div>
        </div>
      </div>
    )
  }

  // group shifts by calendar day
  const byDay = new Map<string, Shift[]>()
  for (const s of shifts) {
    const key = s.starts_at.slice(0, 10)
    byDay.set(key, [...(byDay.get(key) ?? []), s])
  }
  const days = Array.from(byDay.keys()).sort()
  const teamByDay = new Map<string, Shift[]>()
  for (const shift of teamShifts) {
    const key = shift.starts_at.slice(0, 10)
    teamByDay.set(key, [...(teamByDay.get(key) ?? []), shift])
  }
  const teamDays = Array.from(teamByDay.keys()).sort()

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          <CalendarClock className="h-5 w-5 text-zinc-400" /> My Schedule
        </h1>
        <p className="text-sm text-zinc-500 mt-1">Your published shifts for the next four weeks. Request a swap, ask for cover, or flag time you're unavailable.</p>
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-zinc-200">My shifts</h2>
        {days.length === 0 ? (
          <p className="text-sm text-zinc-600">No published shifts in the next four weeks.</p>
        ) : days.map((day) => (
          <div key={day}>
            <div className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wide mb-1.5">{fmtDay(day)}</div>
            <div className="space-y-2">
              {byDay.get(day)!.map((s) => <ShiftCard key={s.id} shift={s} coworkers={coworkers} teamShifts={teamShifts} onChanged={load} />)}
            </div>
          </div>
        ))}
      </section>

      <section className="space-y-3">
        <div>
          <h2 className="text-sm font-medium text-zinc-200">Full schedule</h2>
          <p className="text-[11px] text-zinc-500 mt-0.5">Published team shifts for the next four weeks, including who is assigned.</p>
        </div>
        {teamDays.length === 0 ? (
          <p className="text-sm text-zinc-600">No published team shifts in the next four weeks.</p>
        ) : teamDays.map((day) => (
          <div key={day}>
            <div className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wide mb-1.5">{fmtDay(day)}</div>
            <div className="space-y-2">
              {teamByDay.get(day)!.map((shift) => (
                <div key={shift.id} className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
                  <div className="text-sm font-medium text-zinc-100">{fmtTime(shift.starts_at)}–{fmtTime(shift.ends_at)}</div>
                  {(shift.role || shift.department) && <div className="text-[11px] text-zinc-500">{[shift.role, shift.department].filter(Boolean).join(' · ')}</div>}
                  {shift.notes?.trim() && <p className="mt-1 text-[11px] text-zinc-400 whitespace-pre-wrap">Schedule note: {shift.notes.trim()}</p>}
                  <div className="mt-1 text-[11px] text-zinc-400">{shift.assignments.length ? `Assigned: ${shift.assignments.map((assignment) => assignment.name).join(', ')}` : 'Open shift'}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      {requestError && <p className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-300">{requestError}</p>}

      <AvailabilityEditor />

      <UnavailableForm teamShifts={teamShifts} onDone={load} />

      {offers.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-zinc-200 mb-2">Available offers</h2>
          <div className="space-y-2">
            {offers.map((r) => <OfferCard key={r.id} request={r} shifts={shifts} onChanged={load} />)}
          </div>
        </section>
      )}

      <section>
        <h2 className="text-sm font-medium text-zinc-200 mb-2">My requests</h2>
        {requests.length === 0 ? (
          <p className="text-sm text-zinc-600">No requests yet.</p>
        ) : (
          <div className="space-y-2">
            {requests.map((r) => (
              <div key={r.id} className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
                <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase ${REQUEST_TONE[r.status]}`}>{r.status}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-zinc-200 capitalize">{r.request_type}</div>
                  <div className="text-[11px] text-zinc-500">
                    {r.request_type === 'unavailable'
                      ? `${r.unavailable_start ?? ''} → ${r.unavailable_end ?? ''}`
                      : r.shift_starts_at ? `${fmtDay(r.shift_starts_at)} ${fmtTime(r.shift_starts_at)}` : '—'}
                    {r.reason ? ` · “${r.reason}”` : ''}
                  </div>
                </div>
                {r.can_withdraw !== false && ['pending', 'awaiting_counterparty', 'awaiting_manager'].includes(r.status) && (
                  <button onClick={() => { (r.status === 'pending' ? cancelRequest(r.id) : withdrawMyRequest(r.id).then(load).catch((err) => toast(errorMessage(err), 'error'))) }} className="text-zinc-500 hover:text-red-400 p-1"><X className="h-4 w-4" /></button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function ShiftCard({ shift, coworkers, teamShifts, onChanged }: { shift: Shift; coworkers: { id: string; name: string }[]; teamShifts: Shift[]; onChanged: () => void }) {
  const { toast } = useToast()
  const [mode, setMode] = useState<'swap' | 'pickup' | null>(null)
  const [targetEmployeeId, setTargetEmployeeId] = useState('')
  const [counterShiftId, setCounterShiftId] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const targetShifts = teamShifts.filter((candidate) => (
    candidate.id !== shift.id
    && candidate.assignments.some((assignment) => assignment.employee_id === targetEmployeeId)
  ))

  async function submit() {
    if (!mode) return
    setBusy(true)
    try {
      if (mode === 'swap' && !targetEmployeeId) {
        toast('Choose a coworker for the swap', 'error')
        return
      }
      if (mode === 'swap' && !counterShiftId) {
        toast('Choose the shift you want to trade for', 'error')
        return
      }
      await createMyRequest({ request_type: mode, shift_id: shift.id, target_employee_id: targetEmployeeId || null, counter_shift_id: counterShiftId || null, reason: reason.trim() || null })
      setMode(null)
      setReason('')
      setTargetEmployeeId('')
      setCounterShiftId('')
      toast(`${mode === 'swap' ? 'Swap' : 'Pickup'} offer sent for confirmation`, 'success')
      onChanged()
    } catch (err) {
      toast(errorMessage(err), 'error')
    } finally { setBusy(false) }
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
      <div className="flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-zinc-100 flex items-center gap-1.5">
            {fmtTime(shift.starts_at)}–{fmtTime(shift.ends_at)}
            {shift.kind === 'training' && (
              <span className="px-1.5 py-0.5 rounded-full border text-[9px] font-semibold uppercase text-sky-400 bg-sky-500/10 border-sky-500/20">Training</span>
            )}
          </div>
          {(shift.role || shift.department) && <div className="text-[11px] text-zinc-500 truncate">{[shift.role, shift.department].filter(Boolean).join(' · ')}</div>}
          {shift.notes?.trim() && <p className="mt-1 text-[11px] text-zinc-400 whitespace-pre-wrap">Schedule note: {shift.notes.trim()}</p>}
          <AssignmentGuidance assignment={shift.assignments[0]} />
        </div>
        <button onClick={() => { setMode(mode === 'swap' ? null : 'swap'); setCounterShiftId('') }} className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-100"><Repeat className="h-3.5 w-3.5" /> Swap</button>
        <button onClick={() => setMode(mode === 'pickup' ? null : 'pickup')} className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-100"><LogOut className="h-3.5 w-3.5" /> Offer pickup</button>
      </div>
      {mode && (
        <div className="mt-2 flex items-center gap-2 border-t border-zinc-800 pt-2">
          {mode === 'swap' && <select value={targetEmployeeId} onChange={(e) => { setTargetEmployeeId(e.target.value); setCounterShiftId('') }} className={`${inputCls} max-w-[180px]`}><option value="">Swap with…</option>{coworkers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>}
          {mode === 'swap' && <select value={counterShiftId} disabled={!targetEmployeeId} onChange={(e) => setCounterShiftId(e.target.value)} className={`${inputCls} max-w-[220px] disabled:opacity-40`}><option value="">Trade for their shift…</option>{targetShifts.map((candidate) => <option key={candidate.id} value={candidate.id}>{formatShift(candidate.starts_at, candidate.ends_at, candidate.role, candidate.department)}</option>)}</select>}
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={`Reason for ${mode} (optional)`} className={inputCls} />
          <button onClick={submit} disabled={busy} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs rounded-lg px-2.5 py-1.5 shrink-0 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Send</button>
        </div>
      )}
    </div>
  )
}

function AssignmentGuidance({ assignment }: { assignment: ShiftAssignment | undefined }) {
  if (!assignment) return null
  const guidance = assignment.compliance_guidance
  const summary = guidance?.summary
  const requirements = guidance?.requirements ?? []
  const active = requirements.filter((requirement) => !requirement.waived)
  const waived = requirements.some((requirement) => requirement.waived && requirement.kind === 'meal')
  // Break times a manager staggered and saved. Schedule times are wall-clock,
  // so the characters are already this location's clock — never convert.
  const planned = assignment.planned_breaks ?? []
  return (
    <div className="mt-1.5 space-y-1 text-[11px]">
      {summary && <p className={guidance?.status === 'unmapped' || guidance?.status === 'error' ? 'text-amber-300' : 'text-sky-300'}>{summary}</p>}
      {!summary && active.length > 0 && <p className="text-sky-300">{active.map((requirement) => `${requirement.duration_minutes}-minute ${requirement.paid ? 'paid' : 'unpaid'} ${requirement.kind} break`).join(' · ')}</p>}
      {waived && <p className="text-emerald-300">Meal-break waiver applies to this shift.</p>}
      {planned.length > 0 && <p className="text-sky-300">Scheduled break{planned.length > 1 ? 's' : ''}: {planned.map((entry) => `${entry.start_local.slice(11, 16)} (${entry.duration_minutes} min ${entry.kind})`).join(' · ')}</p>}
      {assignment.manager_note && <p className="text-zinc-400">Manager note: {assignment.manager_note}</p>}
    </div>
  )
}

function OfferCard({ request, shifts, onChanged }: { request: ScheduleRequest; shifts: Shift[]; onChanged: () => void }) {
  const { toast } = useToast()
  const [busy, setBusy] = useState(false)
  const [counterShiftId, setCounterShiftId] = useState('')
  // The API remains authoritative, but do not offer the other employee's
  // shift or a same-day shift that can never pass the conflict check.
  const offeredDay = request.shift_starts_at?.slice(0, 10)
  const hasSelectedCounterShift = request.counter_shift_id !== null
  const tradeableShifts = shifts.filter((shift) => (
    shift.id !== request.shift_id && shift.starts_at.slice(0, 10) !== offeredDay
  ))
  async function accept() {
    setBusy(true)
    try {
      if (request.request_type === 'swap' && !hasSelectedCounterShift && !counterShiftId) {
        toast('Choose your shift to trade', 'error')
        return
      }
      await acceptMyRequest(request.id, hasSelectedCounterShift ? null : counterShiftId || null)
      toast('Offer accepted; waiting for manager approval', 'success')
      onChanged()
    } catch (err) { toast(errorMessage(err), 'error') } finally { setBusy(false) }
  }
  return <div className="flex items-center gap-3 rounded-lg border border-sky-500/20 bg-sky-500/5 p-3">
    <div className="flex-1 min-w-0"><div className="text-sm text-zinc-200">{request.employee_name} · <span className="capitalize">{request.request_type}</span></div><div className="text-[11px] text-zinc-500">Offers: {formatShift(request.shift_starts_at, request.shift_ends_at, request.shift_role, request.shift_department)}{request.reason ? ` · “${request.reason}”` : ''}</div>{hasSelectedCounterShift && <div className="text-[11px] text-zinc-400 mt-0.5">For: {formatShift(request.counter_shift_starts_at, request.counter_shift_ends_at, request.counter_shift_role, request.counter_shift_department)}</div>}</div>
    {request.request_type === 'swap' && !hasSelectedCounterShift && <select value={counterShiftId} onChange={(e) => setCounterShiftId(e.target.value)} className={`${inputCls} max-w-[180px]`}><option value="">Trade my shift…</option>{tradeableShifts.map((s) => <option key={s.id} value={s.id}>{formatShift(s.starts_at, s.ends_at, s.role, s.department)}</option>)}</select>}
    <button onClick={accept} disabled={busy} className="inline-flex items-center gap-1 bg-sky-600 hover:bg-sky-500 text-white text-xs rounded-lg px-2.5 py-1.5 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Accept</button>
  </div>
}

function formatShift(startsAt: string | null | undefined, endsAt: string | null | undefined, role?: string | null, department?: string | null): string {
  if (!startsAt) return '—'
  const details = [role, department].filter(Boolean).join(' · ')
  return [`${fmtDay(startsAt)} ${fmtTime(startsAt)}${endsAt ? `–${fmtTime(endsAt)}` : ''}`, details].filter(Boolean).join(' · ')
}

interface AvailabilityRow { enabled: boolean; start: string; end: string }

const DEFAULT_ROWS: AvailabilityRow[] = WEEKDAY_LABELS.map(() => ({
  enabled: false, start: '09:00', end: '17:00',
}))

function AvailabilityEditor() {
  const { toast } = useToast()
  const [open, setOpen] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [rows, setRows] = useState<AvailabilityRow[]>(DEFAULT_ROWS)
  const [busy, setBusy] = useState(false)

  async function ensureLoaded() {
    if (loaded) return
    try {
      const { windows } = await fetchMyAvailability()
      const next = DEFAULT_ROWS.map((r) => ({ ...r }))
      // v1 edits one window per day — a weekday with multiple stored windows
      // shows only the first; saving overwrites the rest for that day.
      for (const w of windows) {
        next[w.weekday] = { enabled: true, start: w.start_time, end: w.end_time }
      }
      setRows(next)
      setLoaded(true)
    } catch (err) {
      toast(errorMessage(err), 'error')
    }
  }

  async function save() {
    setBusy(true)
    try {
      const windows: AvailabilityWindow[] = rows
        .map((r, weekday) => ({ ...r, weekday }))
        .filter((r) => r.enabled)
        .map((r) => ({ weekday: r.weekday, start_time: r.start, end_time: r.end }))
      await saveMyAvailability(windows)
      toast('Availability saved', 'success')
    } catch (err) {
      toast(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
      <button
        onClick={() => { setOpen((v) => !v); void ensureLoaded() }}
        className="inline-flex items-center gap-2 text-sm text-zinc-200 hover:text-white"
      >
        <Clock className="h-4 w-4 text-zinc-400" /> My weekly availability
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          <p className="text-[11px] text-zinc-500">No days checked = available anytime.</p>
          {rows.map((row, i) => (
            <div key={i} className="flex items-center gap-2">
              <label className="flex items-center gap-1.5 w-14 shrink-0">
                <input
                  type="checkbox" checked={row.enabled}
                  onChange={(e) => setRows((rs) => rs.map((r, j) => j === i ? { ...r, enabled: e.target.checked } : r))}
                />
                <span className="text-xs text-zinc-300">{WEEKDAY_LABELS[i]}</span>
              </label>
              <input
                type="time" value={row.start} disabled={!row.enabled}
                onChange={(e) => setRows((rs) => rs.map((r, j) => j === i ? { ...r, start: e.target.value } : r))}
                className={`${inputCls} disabled:opacity-40`}
              />
              <span className="text-zinc-600">–</span>
              <input
                type="time" value={row.end} disabled={!row.enabled}
                onChange={(e) => setRows((rs) => rs.map((r, j) => j === i ? { ...r, end: e.target.value } : r))}
                className={`${inputCls} disabled:opacity-40`}
              />
            </div>
          ))}
          <button onClick={save} disabled={busy} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs rounded-lg px-3 py-1.5 disabled:opacity-50">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Save
          </button>
        </div>
      )}
    </section>
  )
}

function UnavailableForm({ teamShifts, onDone }: { teamShifts: Shift[]; onDone: () => void }) {
  const { toast } = useToast()
  const [open, setOpen] = useState(false)
  const [from, setFrom] = useState(todayISO())
  const [to, setTo] = useState(todayISO())
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const selectedWeekHasPublishedShifts = teamShifts.some((shift) => {
    const shiftDate = shift.starts_at.slice(0, 10)
    const shiftStart = new Date(`${shiftDate}T00:00:00Z`)
    const weekStart = addDays(toISODate(shiftStart), -shiftStart.getUTCDay())
    const weekEnd = addDays(weekStart, 6)
    return weekStart <= to && weekEnd >= from
  })

  async function submit() {
    setBusy(true)
    try {
      await createMyRequest({
        request_type: 'unavailable',
        unavailable_start: from,
        unavailable_end: to,
        reason: reason.trim() || null,
      })
      setOpen(false)
      setReason('')
      toast('Request sent', 'success')
      onDone()
    } catch (err) {
      toast(errorMessage(err), 'error')
    } finally { setBusy(false) }
  }

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
      <button onClick={() => setOpen((v) => !v)} className="inline-flex items-center gap-2 text-sm text-zinc-200 hover:text-white">
        <CalendarOff className="h-4 w-4 text-zinc-400" /> Request time off / mark unavailable
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          <div className="flex items-end gap-2 flex-wrap">
            <label className="block"><span className="text-[10px] text-zinc-500 uppercase">From</span><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={`${inputCls} mt-1`} /></label>
            <label className="block"><span className="text-[10px] text-zinc-500 uppercase">To</span><input type="date" value={to} onChange={(e) => setTo(e.target.value)} className={`${inputCls} mt-1`} /></label>
          </div>
          {selectedWeekHasPublishedShifts && <p role="alert" className="text-xs text-amber-300">Time-off requests cannot be submitted for a week with published shifts. Choose a different week.</p>}
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} placeholder="Reason (optional)" className={`${inputCls}`} />
          <button onClick={submit} disabled={busy || to < from || selectedWeekHasPublishedShifts} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs rounded-lg px-3 py-1.5 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Submit request</button>
        </div>
      )}
    </section>
  )
}
