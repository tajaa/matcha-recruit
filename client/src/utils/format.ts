/**
 * Shared display formatting.
 *
 * Ten near-copies of "relative time" existed across the app under three names
 * (relativeTime / timeAgo / formatRelative), and they had genuinely drifted:
 * components/dashboard/FlagsTable.tsx stopped at hours, so a 30-day-old flag
 * rendered as "720h ago"; several never fell back to an absolute date, so a
 * year-old row read "412d ago". This is the one implementation.
 *
 * Date formatting lives in ./dateFormat (formatDate / formatDateOnly) — kept
 * separate because formatDateOnly exists to dodge a specific UTC-midnight
 * off-by-one and shouldn't be confused with the general case.
 */

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/**
 * "just now" / "5m ago" / "3h ago" / "6d ago", falling back to an absolute date
 * past 30 days — beyond that a day count stops being something a reader can
 * actually place.
 *
 * Future timestamps clamp to "just now" rather than rendering a negative
 * count: a clock skew of a few seconds between server and browser is normal and
 * "-1m ago" reads as a bug.
 */
export function relativeTime(value: string | number | Date | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const then = value instanceof Date ? value.getTime() : new Date(value).getTime()
  if (Number.isNaN(then)) return '—'

  const diff = Date.now() - then
  if (diff < MINUTE) return 'just now'
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m ago`
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h ago`
  const days = Math.floor(diff / DAY)
  if (days < 30) return `${days}d ago`
  return new Date(then).toLocaleDateString()
}

/**
 * Whole-dollar money for tables and tiles: "$1,250", "-$400", "—" when unset.
 *
 * Cents are dropped deliberately — every existing call site formats premiums,
 * limits and payroll figures where they are noise. Pass `cents: true` for the
 * few places that need them.
 */
export function formatMoney(
  value: number | null | undefined,
  opts: { cents?: boolean } = {},
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const digits = opts.cents ? 2 : 0
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/** "1.2 KB" / "3.4 MB". Base 1024, matching what the upload widgets report. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return '—'
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let v = bytes / 1024
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(1)} ${units[i]}`
}
