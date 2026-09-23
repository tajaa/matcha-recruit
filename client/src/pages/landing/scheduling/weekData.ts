/**
 * The illustrative week the hero composition builds. Fictional store, fictional
 * crew — but the two problems it catches (a 44-hour week and a 7-hour
 * close-to-open turnaround) are ones the real week builder flags, and each fix
 * lands on someone with room in their week.
 */

export const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const
export const DATES = [5, 6, 7, 8, 9, 10, 11] // week of Oct 5

/** Forecast sales per day, from sales history + weather. Saturday is warm. */
export const FORECAST = [4200, 4600, 4800, 5100, 6300, 7900, 5500]
export const SAT = 5

export type Crew = { name: string; role: string; rate: number }

export const CREW: Crew[] = [
  { name: 'Ana R.', role: 'Shift lead', rate: 22 },
  { name: 'Dev P.', role: 'Barista', rate: 18 },
  { name: 'Marisol V.', role: 'Barista', rate: 18 },
  { name: 'Theo K.', role: 'Cook', rate: 20 },
  { name: 'Priya S.', role: 'Cook', rate: 20 },
  { name: 'Jonah B.', role: 'Barista', rate: 17.5 },
  { name: 'Kiko T.', role: 'Prep', rate: 16.5 },
  { name: 'Sam O.', role: 'Barista', rate: 17.5 },
]

export type Shift = {
  id: string
  row: number
  day: number
  start: number // 24h clock, fractional hours
  end: number
  /** Added because of the forecast, not the template. */
  forecast?: boolean
}

const s = (id: string, row: number, day: number, start: number, end: number, forecast?: boolean): Shift => ({
  id,
  row,
  day,
  start,
  end,
  forecast,
})

export const SHIFTS: Shift[] = [
  // Ana — 40h
  s('ana-mon', 0, 0, 6, 14), s('ana-tue', 0, 1, 6, 14), s('ana-thu', 0, 3, 6, 14), s('ana-fri', 0, 4, 14, 22), s('ana-sat', 0, 5, 6, 14),
  // Dev — 40h, Thu close → Fri open is the rest-gap problem
  s('dev-mon', 1, 0, 7, 15), s('dev-tue', 1, 1, 7, 15), s('dev-thu', 1, 3, 15, 23), s('dev-fri', 1, 4, 6, 14), s('dev-sat', 1, 5, 15, 23),
  // Marisol — 44h, the overtime problem
  s('mar-mon', 2, 0, 6, 14), s('mar-tue', 2, 1, 6, 14), s('mar-wed', 2, 2, 6, 14), s('mar-fri', 2, 4, 6, 14), s('mar-sat', 2, 5, 7, 15), s('mar-sun', 2, 6, 10, 14),
  // Theo — 38h
  s('theo-mon', 3, 0, 10, 18), s('theo-tue', 3, 1, 10, 18), s('theo-wed', 3, 2, 10, 16), s('theo-fri', 3, 4, 10, 18), s('theo-sat', 3, 5, 9, 17),
  // Priya — 36h, unavailable Thursday
  s('pri-tue', 4, 1, 14, 20), s('pri-wed', 4, 2, 14, 22), s('pri-fri', 4, 4, 14, 22), s('pri-sat', 4, 5, 11, 19), s('pri-sun', 4, 6, 9, 15),
  // Jonah — 24h (room for the Friday open)
  s('jon-mon', 5, 0, 14, 22), s('jon-wed', 5, 2, 7, 15), s('jon-sat', 5, 5, 10, 18),
  // Kiko — 34h, Saturday shift added for the forecast
  s('kik-wed', 6, 2, 16, 22), s('kik-thu', 6, 3, 10, 18), s('kik-fri', 6, 4, 16, 22), s('kik-sat', 6, 5, 12, 20, true), s('kik-sun', 6, 6, 10, 16),
  // Sam — 30h (room for the Saturday open)
  s('sam-tue', 7, 1, 14, 22), s('sam-wed', 7, 2, 14, 22), s('sam-thu', 7, 3, 14, 22), s('sam-sun', 7, 6, 14, 20),
]

/** A recurring-availability block the draft honours. */
export const UNAVAILABLE = [{ row: 4, day: 3 }]

/** The two fixes the check makes: shift → new row. */
export const MOVES: Record<string, number> = {
  'mar-sat': 7, // Marisol 44h → 36h; Sam 30h → 38h
  'dev-fri': 5, // Dev's 7h turnaround gone; Jonah 24h → 32h
}

export const FLAGS = {
  overtime: { row: 2, shiftId: 'mar-sat', label: '44H · OVER 40' },
  rest: { row: 1, shiftIds: ['dev-thu', 'dev-fri'], label: '7H REST' },
}

const len = (x: Shift) => x.end - x.start

export function weeklyHours(moved: boolean): number[] {
  const hours = CREW.map(() => 0)
  for (const shift of SHIFTS) {
    const row = moved && MOVES[shift.id] !== undefined ? MOVES[shift.id] : shift.row
    hours[row] += len(shift)
  }
  return hours
}

/** Straight-time cost + FLSA weekly overtime premium (half-time over 40h). */
export function laborCost(moved: boolean): { total: number; overtime: number } {
  const hours = weeklyHours(moved)
  let total = 0
  let overtime = 0
  hours.forEach((h, i) => {
    const rate = CREW[i].rate
    const ot = Math.max(0, h - 40)
    total += h * rate + ot * rate * 0.5
    overtime += ot * rate * 0.5
  })
  return { total, overtime }
}

export const FORECAST_TOTAL = FORECAST.reduce((a, b) => a + b, 0)

export function clock(h: number): string {
  const hour = Math.floor(h) % 24
  const suffix = hour < 12 ? 'a' : 'p'
  const twelve = hour % 12 === 0 ? 12 : hour % 12
  return `${twelve}${suffix}`
}

/** Straight-time + weekly OT cost per role, largest first. */
export function laborByRole(moved: boolean): { role: string; people: number; hours: number; cost: number }[] {
  const hours = weeklyHours(moved)
  const byRole = new Map<string, { role: string; people: number; hours: number; cost: number }>()
  CREW.forEach((c, i) => {
    const h = hours[i]
    const ot = Math.max(0, h - 40)
    const row = byRole.get(c.role) ?? { role: c.role, people: 0, hours: 0, cost: 0 }
    row.people += 1
    row.hours += h
    row.cost += h * c.rate + ot * c.rate * 0.5
    byRole.set(c.role, row)
  })
  return [...byRole.values()].sort((a, b) => b.cost - a.cost)
}
