import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { PillTabs } from '../../../components/ui'
import type { Shift } from '../../../types/employeeSchedule'
import { fmtTime } from '../../../types/employeeSchedule'
import { ShiftCard } from './ShiftCard'
import {
  WINDOW_COUNT, buildWindows, fmtDayHeading, fmtWindowLabel, groupByDay, inWindow, todayISO,
} from './shared'

type Scope = 'mine' | 'everyone'

const SCOPE_OPTIONS: { value: Scope; label: string }[] = [
  { value: 'mine', label: 'My shifts' },
  { value: 'everyone', label: 'Everyone' },
]

/** The employee's four-week horizon, one bounded week-length section at a
 *  time. The section index lives in `?week=` so a refresh or a trip through
 *  another tab lands back on the dates the employee was reading. */
export default function ScheduleTab({
  horizonStart, shifts, teamShifts, coworkers, onChanged,
}: {
  /** First day of the fetched horizon — the sections partition it exactly. */
  horizonStart: string
  shifts: Shift[]
  teamShifts: Shift[]
  coworkers: { id: string; name: string }[]
  onChanged: () => void
}) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [scope, setScope] = useState<Scope>('mine')
  const today = todayISO()
  const windows = useMemo(() => buildWindows(horizonStart), [horizonStart])

  // Skip ahead to the first section that actually has one of *their* shifts —
  // an employee whose next shift is a fortnight out should not open on a blank
  // week. Scope-independent so toggling to the team view holds the dates.
  const fallbackIndex = useMemo(() => {
    const found = windows.findIndex((window) => shifts.some((shift) => inWindow(shift, window)))
    return found === -1 ? 0 : found
  }, [windows, shifts])

  const rawWeek = searchParams.get('week')
  const requested = rawWeek === null ? Number.NaN : Number(rawWeek)
  const index = Number.isInteger(requested) && requested >= 0 && requested < WINDOW_COUNT
    ? requested
    : fallbackIndex
  const window = windows[index]

  function goTo(next: number) {
    // replace: a walk through four weeks should not bury the previous page
    // under four history entries.
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev)
      params.set('week', String(next))
      return params
    }, { replace: true })
  }

  const active = scope === 'mine' ? shifts : teamShifts
  const counts = windows.map((candidate) => active.filter((shift) => inWindow(shift, candidate)).length)
  const days = groupByDay(active, window)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <PillTabs size="sm" options={SCOPE_OPTIONS} value={scope} onChange={setScope} />
        <div className="flex items-center gap-1">
          <button
            type="button" aria-label="Previous week" disabled={index === 0}
            onClick={() => goTo(index - 1)}
            className="p-1 rounded text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 disabled:opacity-30 disabled:hover:bg-transparent"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-sm text-zinc-200 tabular-nums text-center min-w-[8.5rem]">{fmtWindowLabel(window)}</span>
          <button
            type="button" aria-label="Next week" disabled={index === WINDOW_COUNT - 1}
            onClick={() => goTo(index + 1)}
            className="p-1 rounded text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 disabled:opacity-30 disabled:hover:bg-transparent"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="flex gap-1.5 overflow-x-auto pb-1" role="group" aria-label="Jump to a week">
        {windows.map((candidate, i) => (
          <button
            key={candidate.from}
            type="button"
            aria-pressed={i === index}
            onClick={() => goTo(i)}
            className={`shrink-0 inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] transition-colors ${
              i === index
                ? 'border-zinc-600 bg-zinc-800 text-zinc-100'
                : 'border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:text-zinc-100 hover:border-zinc-700'
            }`}
          >
            <span>{fmtWindowLabel(candidate)}</span>
            <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
              counts[i] ? 'bg-emerald-500/15 text-emerald-300' : 'bg-zinc-800 text-zinc-600'
            }`}>{counts[i]}</span>
          </button>
        ))}
      </div>

      <section className="space-y-3">
        <div>
          <h2 className="text-sm font-medium text-zinc-200">{scope === 'mine' ? 'My shifts' : 'Full schedule'}</h2>
          <p className="text-[11px] text-zinc-500 mt-0.5">
            {scope === 'mine'
              ? 'Your published shifts for this week. Request a swap or offer a pickup from any shift.'
              : 'Published team shifts for this week, including who is assigned.'}
          </p>
        </div>
        {days.length === 0 ? (
          <p className="text-sm text-zinc-600">
            {scope === 'mine' ? 'No published shifts' : 'No published team shifts'} for {fmtWindowLabel(window)}.
          </p>
        ) : days.map(([day, dayShifts]) => (
          <div key={day}>
            <div className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wide mb-1.5">{fmtDayHeading(day, today)}</div>
            <div className="space-y-2">
              {scope === 'mine'
                ? dayShifts.map((shift) => (
                  <ShiftCard key={shift.id} shift={shift} coworkers={coworkers} teamShifts={teamShifts} onChanged={onChanged} />
                ))
                : dayShifts.map((shift) => (
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
    </div>
  )
}
