/** "Oct 4 – 10, 2026" (or "Sep 28 – Oct 4, 2026") for an ISO week start. */
export function weekRangeLabel(weekStart: string): string {
  const start = new Date(`${weekStart}T00:00:00Z`)
  if (Number.isNaN(start.getTime())) return `Week of ${weekStart}`
  const end = new Date(start.getTime() + 6 * 86_400_000)
  const month = (date: Date) => date.toLocaleDateString('en-US', { month: 'short', timeZone: 'UTC' })
  const tail = start.getUTCMonth() === end.getUTCMonth() ? `${end.getUTCDate()}` : `${month(end)} ${end.getUTCDate()}`
  const year = start.getUTCFullYear() === end.getUTCFullYear() ? '' : `, ${start.getUTCFullYear()}`
  return `${month(start)} ${start.getUTCDate()}${year} – ${tail}, ${end.getUTCFullYear()}`
}
