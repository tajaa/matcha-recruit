import type { BreakReminderEvent } from '../../types/employeeSchedule'

/** Break times are the store's clock face — render the characters, never convert. */
export function wallClock(startLocal: string | null | undefined): string {
  const match = /T(\d{2}):(\d{2})/.exec(startLocal ?? '')
  if (!match) return '—'
  const hour = Number(match[1])
  return `${hour % 12 || 12}:${match[2]} ${hour < 12 ? 'AM' : 'PM'}`
}

export function formatDay(day: string): string {
  const [year, month, date] = day.split('-').map(Number)
  if (!year || !month || !date) return day
  return new Date(year, month - 1, date).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

/** Send time in the location's own zone, since that is the clock a wage-and-hour review reads. */
export function formatOccurredAt(event: BreakReminderEvent): string {
  const date = new Date(event.occurred_at)
  if (Number.isNaN(date.getTime())) return event.occurred_at
  // Explicit fields: dateStyle/timeStyle refuse to combine with timeZoneName.
  const options: Intl.DateTimeFormatOptions = {
    year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
  }
  try {
    return date.toLocaleString(undefined, { ...options, timeZone: event.location?.timezone ?? undefined })
  } catch {
    // An unrecognised stored zone: fall back to the viewer's, still labelled.
    return date.toLocaleString(undefined, options)
  }
}

export function breakText(kind: string | undefined, startLocal: string | undefined | null, minutes: number | null | undefined): string {
  const label = kind === 'rest' ? 'Rest' : kind === 'meal' ? 'Meal' : 'Break'
  return `${label} ${wallClock(startLocal)}${minutes ? ` (${minutes} min)` : ''}`
}

export function reminderText(event: BreakReminderEvent): string {
  if (event.reminder_type === 'break_start') {
    return event.break ? `Break start · ${breakText(event.break.kind, event.break.start_local, event.break.duration_minutes)}` : 'Break start'
  }
  if (event.recipient_type === 'manager') {
    const count = event.context.employees_with_break_content ?? event.covered_employee_count
    return `Daily digest · lists ${count} employee${count === 1 ? '' : 's'}' breaks`
  }
  const breaks = event.context.breaks ?? []
  return breaks.length
    ? `Daily digest · ${breaks.map((entry) => breakText(entry.kind, entry.start_local, entry.duration_minutes)).join(', ')}`
    : 'Daily digest · break requirements'
}
