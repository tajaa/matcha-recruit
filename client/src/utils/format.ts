/**
 * Shared display formatting.
 *
 * Ten near-copies of "relative time" existed across the app under three names
 * (relativeTime / timeAgo / formatRelative). Some of that was genuine drift —
 * components/dashboard/FlagsTable.tsx stopped at hours, so a 30-day-old flag
 * rendered "720h ago". But some of it was NOT drift: an inbox list wants
 * "Yesterday" and a bare date, a notification dropdown wants a sentence-cased
 * "Just now" and a narrow "Mar 5", a public blog wants an absolute date after a
 * week. Those are presentation decisions for a specific surface.
 *
 * So this is one implementation with named options rather than one fixed
 * output. Every option below exists because a real call site needed it; the
 * defaults are what the majority of sites already did.
 *
 * Date formatting lives in ./dateFormat (formatDate / formatDateOnly) — kept
 * separate because formatDateOnly exists to dodge a specific UTC-midnight
 * off-by-one and shouldn't be confused with the general case.
 */

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

export type RelativeTimeOptions = {
  /** Rendered for null/undefined input. Lists that show nothing pass ''. */
  empty?: string
  /** Under one minute. Sentence-cased surfaces pass 'Just now'. */
  justNowLabel?: string
  /**
   * Label for exactly one day ago. Omitted by default — only surfaces that
   * previously special-cased it (inbox, notifications, channel analytics) pass
   * one, and they disagree on casing, hence a label rather than a boolean.
   */
  yesterdayLabel?: string
  /**
   * Switch to an absolute date past this many days. Default 30. Pass Infinity
   * to count days forever (channel analytics does).
   */
  maxRelativeDays?: number
  /** Absolute rendering past the cutoff. Default `toLocaleDateString()`. */
  absolute?: (d: Date) => string
  /** Unparseable input. Default returns `empty`; blog comments echo the raw string. */
  onInvalid?: (raw: string | number | Date) => string
}

/**
 * "just now" / "5m ago" / "3h ago" / "6d ago", falling back to an absolute date
 * past `maxRelativeDays` — beyond that a day count stops being something a
 * reader can place.
 *
 * Future timestamps clamp to the just-now label rather than rendering a
 * negative count: a few seconds of clock skew between server and browser is
 * normal, and "-1m ago" reads as a bug.
 */
export function relativeTime(
  value: string | number | Date | null | undefined,
  opts: RelativeTimeOptions = {},
): string {
  const {
    empty = '—',
    justNowLabel = 'just now',
    yesterdayLabel,
    maxRelativeDays = 30,
    absolute = (d: Date) => d.toLocaleDateString(),
    onInvalid,
  } = opts

  if (value === null || value === undefined) return empty
  const then = value instanceof Date ? value.getTime() : new Date(value).getTime()
  if (Number.isNaN(then)) return onInvalid ? onInvalid(value) : empty

  const diff = Date.now() - then
  if (diff < MINUTE) return justNowLabel
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m ago`
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h ago`

  const days = Math.floor(diff / DAY)
  if (days === 1 && yesterdayLabel) return yesterdayLabel
  if (days < maxRelativeDays) return `${days}d ago`
  return absolute(new Date(then))
}

/** `{month:'short', day:'numeric'}` — "Mar 5". Narrow lists and dropdowns. */
export const shortDate = (d: Date) =>
  d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

/** `{year,month,day}` — "Mar 5, 2026". Long-lived public content. */
export const shortDateWithYear = (d: Date) =>
  d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })

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
