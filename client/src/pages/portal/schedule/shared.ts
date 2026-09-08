// Shared plumbing for the employee-portal schedule tabs.
//
// The portal renders the same shifts the admin grid does, so every time
// format here delegates to `types/employeeSchedule` rather than re-deriving
// one (see the UTC wall-clock note there).

import { addDays, fmtDayLabel, fmtTime, toISODate } from '../../../types/employeeSchedule'
import type { Shift } from '../../../types/employeeSchedule'

/** How far ahead the portal fetches published shifts. */
export const HORIZON_DAYS = 28
/** One bounded section of that horizon — what a tab shows at a time. */
export const WINDOW_DAYS = 7
export const WINDOW_COUNT = HORIZON_DAYS / WINDOW_DAYS

export const inputCls =
  'bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 w-full'

export function todayISO(): string {
  return toISODate(new Date())
}

export interface DateWindow {
  from: string
  to: string
}

/** The horizon split into consecutive `WINDOW_DAYS` sections anchored on
 *  `start` (today). Deliberately NOT calendar-week aligned: the portal has no
 *  location scheduling profile in hand, so it cannot know which weekday a
 *  store starts its week on — the same caveat the time-off pre-warning
 *  carries. Anchoring on today also keeps the sections covering exactly the
 *  fetched horizon, with no half-empty leading section. */
export function buildWindows(start: string): DateWindow[] {
  return Array.from({ length: WINDOW_COUNT }, (_, i) => {
    const from = addDays(start, i * WINDOW_DAYS)
    return { from, to: addDays(from, WINDOW_DAYS - 1) }
  })
}

export function inWindow(shift: Shift, window: DateWindow): boolean {
  const day = shift.starts_at.slice(0, 10)
  return day >= window.from && day <= window.to
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function monthDay(iso: string): { month: string; day: number } {
  const d = new Date(`${iso}T00:00:00Z`)
  return { month: MONTHS[d.getUTCMonth()], day: d.getUTCDate() }
}

/** "Aug 24 – 30", or "Aug 31 – Sep 6" across a month boundary. */
export function fmtWindowLabel({ from, to }: DateWindow): string {
  const a = monthDay(from)
  const b = monthDay(to)
  return a.month === b.month
    ? `${a.month} ${a.day} – ${b.day}`
    : `${a.month} ${a.day} – ${b.month} ${b.day}`
}

/** "Fri 8/28 · Today" — the day label plus where it sits relative to today. */
export function fmtDayHeading(day: string, today: string): string {
  const label = fmtDayLabel(day)
  if (day === today) return `${label} · Today`
  if (day === addDays(today, 1)) return `${label} · Tomorrow`
  return label
}

/** Shifts falling inside `window`, grouped by calendar day, days ascending. */
export function groupByDay(shifts: Shift[], window: DateWindow): [string, Shift[]][] {
  const byDay = new Map<string, Shift[]>()
  for (const shift of shifts) {
    if (!inWindow(shift, window)) continue
    const key = shift.starts_at.slice(0, 10)
    byDay.set(key, [...(byDay.get(key) ?? []), shift])
  }
  return Array.from(byDay.entries()).sort(([a], [b]) => a.localeCompare(b))
}

export function formatShift(
  startsAt: string | null | undefined,
  endsAt: string | null | undefined,
  role?: string | null,
  department?: string | null,
): string {
  if (!startsAt) return '—'
  const details = [role, department].filter(Boolean).join(' · ')
  return [`${fmtDayLabel(startsAt)} ${fmtTime(startsAt)}${endsAt ? `–${fmtTime(endsAt)}` : ''}`, details]
    .filter(Boolean)
    .join(' · ')
}
