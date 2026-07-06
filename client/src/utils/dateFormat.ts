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
