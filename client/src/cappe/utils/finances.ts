// Date windows for the Finances page.

export type Range = '7' | '30' | '90' | '365' | 'custom'

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** The [start, end] dates for a preset, ending today (the browser's today —
 *  the server reads them in the store's own timezone). */
export function presetWindow(range: Exclude<Range, 'custom'>, today = new Date()): [string, string] {
  const start = new Date(today)
  start.setDate(start.getDate() - (Number(range) - 1))
  return [iso(start), iso(today)]
}

/** Day buckets for a short window, weeks up to ~4 months, months beyond. */
export function groupFor(start: string, end: string): 'day' | 'week' | 'month' {
  const days = (Date.parse(end) - Date.parse(start)) / 86_400_000 + 1
  return days <= 45 ? 'day' : days <= 120 ? 'week' : 'month'
}

