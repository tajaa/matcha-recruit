import { useCallback, useState } from 'react'
import { CalendarOff, Check, Loader2, X } from 'lucide-react'
import { useToast } from '../../../components/ui'
import {
  acceptMyRequest, cancelMyRequest, createMyRequest, withdrawMyRequest,
} from '../../../api/employees/employeeSchedule'
import type { ScheduleRequest, Shift } from '../../../types/employeeSchedule'
import {
  REQUEST_TONE, addDays, describeProposedAvailability, errorMessage, fmtDayLabel as fmtDay, fmtTime, toISODate,
} from '../../../types/employeeSchedule'
import { formatShift, inputCls, todayISO } from './shared'

const WITHDRAWABLE = ['pending', 'awaiting_counterparty', 'awaiting_manager']

/** Everything the employee has asked for or been asked about: offers waiting on
 *  them, the time-off / unavailable form, and their own request history. */
export default function RequestsTab({
  requests, offers, shifts, teamShifts, onChanged,
}: {
  requests: ScheduleRequest[]
  offers: ScheduleRequest[]
  shifts: Shift[]
  teamShifts: Shift[]
  onChanged: () => void
}) {
  const { toast } = useToast()

  const cancelRequest = useCallback(async (id: string) => {
    try {
      await cancelMyRequest(id)
      onChanged()
    } catch (err) {
      toast(errorMessage(err), 'error')
    }
  }, [onChanged, toast])

  return (
    <div className="space-y-6">
      {offers.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-zinc-200 mb-2">Available offers</h2>
          <div className="space-y-2">
            {offers.map((r) => <OfferCard key={r.id} request={r} shifts={shifts} onChanged={onChanged} />)}
          </div>
        </section>
      )}

      <UnavailableForm teamShifts={teamShifts} onDone={onChanged} />

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
                      : r.request_type === 'availability'
                        ? `From ${r.availability_effective_on ?? '—'} · ${describeProposedAvailability(r.proposed_availability)}`
                        : r.shift_starts_at ? `${fmtDay(r.shift_starts_at)} ${fmtTime(r.shift_starts_at)}` : '—'}
                    {r.reason ? ` · “${r.reason}”` : ''}
                  </div>
                </div>
                {r.can_withdraw !== false && WITHDRAWABLE.includes(r.status) && (
                  <button
                    aria-label="Withdraw request"
                    onClick={() => {
                      // `pending` never reached a counterparty, so it is a plain
                      // cancel; anything further along is a withdrawal.
                      if (r.status === 'pending') { void cancelRequest(r.id); return }
                      void withdrawMyRequest(r.id).then(onChanged).catch((err) => toast(errorMessage(err), 'error'))
                    }}
                    className="text-zinc-500 hover:text-red-400 p-1"
                  ><X className="h-4 w-4" /></button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
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
  return <div className="flex items-center gap-3 flex-wrap rounded-lg border border-sky-500/20 bg-sky-500/5 p-3">
    <div className="flex-1 min-w-0"><div className="text-sm text-zinc-200">{request.employee_name} · <span className="capitalize">{request.request_type}</span></div><div className="text-[11px] text-zinc-500">Offers: {formatShift(request.shift_starts_at, request.shift_ends_at, request.shift_role, request.shift_department)}{request.reason ? ` · “${request.reason}”` : ''}</div>{hasSelectedCounterShift && <div className="text-[11px] text-zinc-400 mt-0.5">For: {formatShift(request.counter_shift_starts_at, request.counter_shift_ends_at, request.counter_shift_role, request.counter_shift_department)}</div>}</div>
    {request.request_type === 'swap' && !hasSelectedCounterShift && <select value={counterShiftId} onChange={(e) => setCounterShiftId(e.target.value)} className={`${inputCls} max-w-[180px]`}><option value="">Trade my shift…</option>{tradeableShifts.map((s) => <option key={s.id} value={s.id}>{formatShift(s.starts_at, s.ends_at, s.role, s.department)}</option>)}</select>}
    <button onClick={accept} disabled={busy} className="inline-flex items-center gap-1 bg-sky-600 hover:bg-sky-500 text-white text-xs rounded-lg px-2.5 py-1.5 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Accept</button>
  </div>
}

function UnavailableForm({ teamShifts, onDone }: { teamShifts: Shift[]; onDone: () => void }) {
  const { toast } = useToast()
  const [open, setOpen] = useState(false)
  const [from, setFrom] = useState(todayISO())
  const [to, setTo] = useState(todayISO())
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  // Advisory only — it warns before submitting. The authoritative check is
  // the server's time_off_guard, which anchors each shift on ITS OWN
  // location's week start; the portal has no location profile in hand, so
  // this pre-warning stays Sunday-anchored and can differ by a day for a
  // store that starts its week elsewhere.
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
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} placeholder="Reason (optional)" className={inputCls} />
          <button onClick={submit} disabled={busy || to < from || selectedWeekHasPublishedShifts} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs rounded-lg px-3 py-1.5 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Submit request</button>
        </div>
      )}
    </section>
  )
}
