/** Is this effective date still in the future — i.e. researched and current in
 *  the catalog, but not yet law? Date-only compare: `effective_date` is a DATE,
 *  so parsing it gives UTC midnight, and comparing that against `new Date()`
 *  would flip the label early or late depending on the viewer's timezone. */
export function isFuture(effectiveDate: string): boolean {
  const eff = new Date(effectiveDate)
  if (Number.isNaN(eff.getTime())) return false
  const today = new Date()
  const todayUTC = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  return Date.UTC(eff.getUTCFullYear(), eff.getUTCMonth(), eff.getUTCDate()) > todayUTC
}
