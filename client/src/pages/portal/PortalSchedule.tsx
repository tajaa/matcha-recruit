import { useEffect, useState, useCallback } from 'react'
import { CalendarClock, Loader2, X, Check, Repeat, LogOut, CalendarOff } from 'lucide-react'
import {
  fetchMySchedule, fetchMyRequests, createMyRequest, cancelMyRequest,
} from '../../api/employeeSchedule'
import type { Shift, ScheduleRequest } from '../../types/employeeSchedule'
import { WEEKDAY_LABELS, REQUEST_TONE } from '../../types/employeeSchedule'

function fmtTime(iso: string): string {
  const d = new Date(iso)
  let h = d.getUTCHours()
  const m = d.getUTCMinutes()
  const ap = h >= 12 ? 'p' : 'a'
  h = h % 12 || 12
  return m ? `${h}:${String(m).padStart(2, '0')}${ap}` : `${h}${ap}`
}
function fmtDay(iso: string): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`)
  return `${WEEKDAY_LABELS[d.getUTCDay()]}, ${d.getUTCMonth() + 1}/${d.getUTCDate()}`
}
function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}
function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

const inputCls = 'bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 w-full'

export default function PortalSchedule() {
  const [shifts, setShifts] = useState<Shift[]>([])
  const [requests, setRequests] = useState<ScheduleRequest[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    const start = todayISO()
    const [sch, reqs] = await Promise.all([
      fetchMySchedule(`${start}T00:00:00Z`, `${addDays(start, 28)}T00:00:00Z`),
      fetchMyRequests(),
    ])
    setShifts(sch.shifts)
    setRequests(reqs.requests)
  }, [])

  useEffect(() => { load().finally(() => setLoading(false)) }, [load])

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>

  // group shifts by calendar day
  const byDay = new Map<string, Shift[]>()
  for (const s of shifts) {
    const key = s.starts_at.slice(0, 10)
    byDay.set(key, [...(byDay.get(key) ?? []), s])
  }
  const days = Array.from(byDay.keys()).sort()

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          <CalendarClock className="h-5 w-5 text-zinc-400" /> My Schedule
        </h1>
        <p className="text-sm text-zinc-500 mt-1">Your published shifts for the next four weeks. Request a swap, ask for cover, or flag time you're unavailable.</p>
      </div>

      <section className="space-y-3">
        {days.length === 0 ? (
          <p className="text-sm text-zinc-600">No published shifts in the next four weeks.</p>
        ) : days.map((day) => (
          <div key={day}>
            <div className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wide mb-1.5">{fmtDay(day)}</div>
            <div className="space-y-2">
              {byDay.get(day)!.map((s) => <ShiftCard key={s.id} shift={s} onChanged={load} />)}
            </div>
          </div>
        ))}
      </section>

      <UnavailableForm onDone={load} />

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
                {r.status === 'pending' && (
                  <button onClick={async () => { await cancelMyRequest(r.id); load() }} className="text-zinc-500 hover:text-red-400 p-1"><X className="h-4 w-4" /></button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function ShiftCard({ shift, onChanged }: { shift: Shift; onChanged: () => void }) {
  const [mode, setMode] = useState<'swap' | 'drop' | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (!mode) return
    setBusy(true)
    try {
      await createMyRequest({ request_type: mode, shift_id: shift.id, reason: reason.trim() || null })
      setMode(null)
      setReason('')
      onChanged()
    } finally { setBusy(false) }
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
      <div className="flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-zinc-100">{fmtTime(shift.starts_at)}–{fmtTime(shift.ends_at)}</div>
          {(shift.role || shift.department) && <div className="text-[11px] text-zinc-500 truncate">{[shift.role, shift.department].filter(Boolean).join(' · ')}</div>}
        </div>
        <button onClick={() => setMode(mode === 'swap' ? null : 'swap')} className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-100"><Repeat className="h-3.5 w-3.5" /> Swap</button>
        <button onClick={() => setMode(mode === 'drop' ? null : 'drop')} className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-100"><LogOut className="h-3.5 w-3.5" /> Drop</button>
      </div>
      {mode && (
        <div className="mt-2 flex items-center gap-2 border-t border-zinc-800 pt-2">
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={`Reason for ${mode} (optional)`} className={inputCls} />
          <button onClick={submit} disabled={busy} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs rounded-lg px-2.5 py-1.5 shrink-0 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Send</button>
        </div>
      )}
    </div>
  )
}

function UnavailableForm({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [from, setFrom] = useState(todayISO())
  const [to, setTo] = useState(todayISO())
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

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
      onDone()
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
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} placeholder="Reason (optional)" className={`${inputCls}`} />
          <button onClick={submit} disabled={busy || to < from} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs rounded-lg px-3 py-1.5 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Submit request</button>
        </div>
      )}
    </section>
  )
}
