/**
 * Format a date string for display in tables and lists.
 * - Same year: "May 15"
 * - Different year: "May 15, 2025"
 * - Null/empty: "—"
 */
// Hoisted: Intl.DateTimeFormat construction is ~100x the cost of .format()
// and this runs per-row in tables.
const _sameYear = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' })
const _withYear = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' })

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (isNaN(d.getTime())) return '—'
  const now = new Date()
  if (d.getFullYear() === now.getFullYear()) {
    return _sameYear.format(d)
  }
  return _withYear.format(d)
}

/**
 * Format a calendar date that carries no time — a Postgres DATE column,
 * serialized as "YYYY-MM-DD".
 *
 * `new Date("2027-07-09")` is parsed as UTC midnight, which renders as the
 * *previous* day everywhere west of Greenwich. Build the date from its parts so
 * it lands on local midnight and the displayed day matches what's stored.
 */
export function formatDateOnly(value: string | null | undefined): string {
  if (!value) return '—'
  const [y, m, d] = value.slice(0, 10).split('-').map(Number)
  if (!y || !m || !d) return '—'
  return new Date(y, m - 1, d).toLocaleDateString()
}

/**
 * Format a timestamp with time-of-day, forced to Pacific regardless of the
 * viewer's own device timezone — this surface (matcha-work threads) is an
 * internal ops tool where "when was this made" needs one consistent
 * reference clock, not whatever timezone a given browser happens to be in.
 * "Aug 5, 2:07 PM PT" / with year when not the current one.
 */
// timeZoneName: 'short' emits the correct PST/PDT for the given instant —
// hardcoding "PT" would be wrong on one side of the DST boundary.
const _pacificSameYear = new Intl.DateTimeFormat('en-US', {
  month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/Los_Angeles', timeZoneName: 'short',
})
const _pacificWithYear = new Intl.DateTimeFormat('en-US', {
  month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/Los_Angeles', timeZoneName: 'short',
})

export function formatDateTimePacific(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (isNaN(d.getTime())) return '—'
  const now = new Date()
  return (d.getFullYear() === now.getFullYear() ? _pacificSameYear : _pacificWithYear).format(d)
}
