// Formatting for agent-card flight results (server: agent_card/flights.py).
//
// Times come as the airport's local wall-clock time with no offset
// ("2026-11-12T07:05:00"), so they are read as text, never through Date and
// the viewer's own time zone.

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

/** "2026-11-12T07:05:00" → "7:05am". */
export function flightClock(iso: string): string {
  const match = /T(\d{2}):(\d{2})/.exec(iso)
  if (!match) return ''
  const hour = Number(match[1])
  return `${hour % 12 || 12}:${match[2]}${hour < 12 ? 'am' : 'pm'}`
}

/** "2026-11-12T07:05:00" → "Thu, Nov 12". */
export function flightDay(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!match) return ''
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])]
  // UTC math on the calendar date alone: no time zone can shift the weekday.
  const weekday = WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()]
  return `${weekday}, ${MONTHS[month - 1]} ${day}`
}

/** Calendar days between departure and arrival: the "+1" on a red-eye. */
export function dayOffset(departingAt: string, arrivingAt: string): number {
  const toDay = (iso: string) => {
    const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
    return match ? Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])) : Number.NaN
  }
  const days = Math.round((toDay(arrivingAt) - toDay(departingAt)) / 86_400_000)
  return Number.isFinite(days) ? days : 0
}

/** 335 → "5h 35m". */
export function flightDuration(minutes: number | null | undefined): string {
  if (minutes == null) return ''
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h ? `${h}h${m ? ` ${m}m` : ''}` : `${m}m`
}

export function stopsText(stops: number): string {
  return stops === 0 ? 'Nonstop' : `${stops} stop${stops === 1 ? '' : 's'}`
}

/** "310.00" + "USD" → "$310.00" (falls back to "310.00 XYZ"). */
export function fareText(amount: string | null | undefined, currency: string): string {
  if (amount == null) return ''
  const value = Number(amount)
  if (!Number.isFinite(value)) return amount
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: currency || 'USD' }).format(value)
  } catch {
    return `${value.toFixed(2)} ${currency}`
  }
}
