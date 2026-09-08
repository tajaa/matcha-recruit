import { useEffect, useState } from 'react'
import { AlertTriangle, Check, Loader2 } from 'lucide-react'
import { useToast } from '../../../components/ui'
import {
  fetchMyAvailability, submitMyAvailabilityRequest, type AvailabilityWindow,
} from '../../../api/employees/employeeSchedule'
import type { ScheduleRequest, Shift } from '../../../types/employeeSchedule'
import {
  WEEKDAY_LABELS, addDays, describeProposedAvailability, errorMessage, toISODate,
} from '../../../types/employeeSchedule'
import { inputCls, todayISO } from './shared'

interface AvailabilityRow { enabled: boolean; start: string; end: string }

const DEFAULT_ROWS: AvailabilityRow[] = WEEKDAY_LABELS.map(() => ({
  enabled: false, start: '09:00', end: '17:00',
}))

/** The employee's standing weekly availability. It is a *request* — the
 *  manager approves before it takes effect — so this tab never writes the
 *  availability rows directly. */
export default function AvailabilityTab({ teamShifts, onSubmitted }: { teamShifts: Shift[]; onSubmitted: () => void }) {
  const { toast } = useToast()
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [rows, setRows] = useState<AvailabilityRow[]>(DEFAULT_ROWS)
  const [pending, setPending] = useState<ScheduleRequest | null>(null)
  // Two weeks out by default: a start date inside an already published week is
  // refused, and the published horizon is usually the next week or two.
  const [effectiveOn, setEffectiveOn] = useState(() => addDays(todayISO(), 14))
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchMyAvailability()
      .then(({ windows, pending_request }) => {
        if (cancelled) return
        const next = DEFAULT_ROWS.map((r) => ({ ...r }))
        // v1 edits one window per day — a weekday with multiple stored windows
        // shows only the first; submitting replaces the rest for that day.
        for (const w of windows) {
          next[w.weekday] = { enabled: true, start: w.start_time, end: w.end_time }
        }
        setRows(next)
        setPending(pending_request)
      })
      .catch((err) => { if (!cancelled) setLoadError(errorMessage(err)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  // Advisory only, same caveat as the time-off form: the server anchors each
  // shift on its own location's week start, and the portal has no location
  // profile in hand, so this pre-warning stays Sunday-anchored.
  const startsInPublishedWeek = teamShifts.some((shift) => {
    const shiftDate = shift.starts_at.slice(0, 10)
    const shiftStart = new Date(`${shiftDate}T00:00:00Z`)
    const weekStart = addDays(toISODate(shiftStart), -shiftStart.getUTCDay())
    return weekStart <= effectiveOn && addDays(weekStart, 6) >= effectiveOn
  })

  async function submit() {
    setBusy(true)
    try {
      const windows: AvailabilityWindow[] = rows
        .map((r, weekday) => ({ ...r, weekday }))
        .filter((r) => r.enabled)
        .map((r) => ({ weekday: r.weekday, start_time: r.start, end_time: r.end }))
      const request = await submitMyAvailabilityRequest({
        availability: {
          availability_state: windows.length ? 'windows' : 'always_available',
          windows,
        },
        effective_on: effectiveOn,
        reason: reason.trim() || null,
      })
      setPending(request)
      setReason('')
      toast('Availability change sent to your manager', 'success')
      onSubmitted()
    } catch (err) {
      toast(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-40"><Loader2 className="h-5 w-5 text-zinc-500 animate-spin" /></div>
  }

  if (loadError) {
    return (
      <div className="flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/5 p-4">
        <AlertTriangle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
        <div>
          <div className="text-sm font-medium text-zinc-100">Couldn’t load your availability</div>
          <div className="text-sm text-zinc-400 mt-0.5">{loadError}</div>
        </div>
      </div>
    )
  }

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-sm font-medium text-zinc-200">My weekly availability</h2>
        <p className="text-[11px] text-zinc-500 mt-0.5">
          No days checked = available anytime. Your manager approves the change before it takes effect.
        </p>
      </div>

      {pending && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5 text-[11px] text-amber-200">
          <div className="font-medium">Awaiting manager approval</div>
          <div className="mt-0.5 text-amber-300/80">
            Starts {pending.availability_effective_on ?? '—'} · {describeProposedAvailability(pending.proposed_availability)}
          </div>
          <div className="mt-0.5 text-amber-300/80">
            Withdraw it in the “My Requests” tab to propose something else.
          </div>
        </div>
      )}

      <div className="space-y-2">
        {rows.map((row, i) => (
          <div key={i} className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 w-14 shrink-0">
              <input
                type="checkbox" checked={row.enabled} disabled={!!pending}
                onChange={(e) => setRows((rs) => rs.map((r, j) => j === i ? { ...r, enabled: e.target.checked } : r))}
              />
              <span className="text-xs text-zinc-300">{WEEKDAY_LABELS[i]}</span>
            </label>
            <input
              type="time" value={row.start} disabled={!row.enabled || !!pending}
              onChange={(e) => setRows((rs) => rs.map((r, j) => j === i ? { ...r, start: e.target.value } : r))}
              className={`${inputCls} disabled:opacity-40`}
            />
            <span className="text-zinc-600">–</span>
            <input
              type="time" value={row.end} disabled={!row.enabled || !!pending}
              onChange={(e) => setRows((rs) => rs.map((r, j) => j === i ? { ...r, end: e.target.value } : r))}
              className={`${inputCls} disabled:opacity-40`}
            />
          </div>
        ))}
      </div>

      <label className="block max-w-[220px]">
        <span className="text-[10px] text-zinc-500 uppercase">Starts on</span>
        <input
          type="date" value={effectiveOn} min={todayISO()} disabled={!!pending}
          onChange={(e) => setEffectiveOn(e.target.value)}
          className={`${inputCls} mt-1 disabled:opacity-40`}
        />
      </label>
      {startsInPublishedWeek && (
        <p role="alert" className="text-xs text-amber-300">
          That week is already published. Pick a start date in a week that hasn’t been published yet.
        </p>
      )}
      <textarea
        value={reason} onChange={(e) => setReason(e.target.value)} rows={2}
        placeholder="Reason (optional)" disabled={!!pending}
        className={`${inputCls} disabled:opacity-40`}
      />
      <button
        onClick={submit}
        disabled={busy || !!pending || !effectiveOn || effectiveOn < todayISO() || startsInPublishedWeek}
        className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs rounded-lg px-3 py-1.5 disabled:opacity-50"
      >
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Send for approval
      </button>
    </section>
  )
}
