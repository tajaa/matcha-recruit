export function formatDate(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export function formatDays(d: number): string {
  if (d === 0) return 'today'
  if (d === 1) return 'tomorrow'
  if (d === -1) return '1 day overdue'
  if (d < 0) return `${Math.abs(d)} days overdue`
  return `in ${d} days`
}

// Format a Date as 'YYYY-MM-DD' in *local* time. Using `toISOString()` here
// would convert to UTC and shift the date by ±1 day in many timezones,
// causing cell keys never to match server-provided deadlines (which are
// already 'YYYY-MM-DD' with no timezone). The bug surfaced as an
// always-empty Month view for users in any non-near-UTC timezone — and
// even in PST it was still wrong on month boundaries.
export function localDateKey(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}
