// Strict money parsing for owner-facing amount inputs.
//
// `parseFloat` is wrong for money twice over: it truncates at the first
// non-numeric character, so "12.5.7" silently becomes 12.5 and "1,299" becomes
// 1 — a $1,299 product saved as $1.00 — and it accepts "12abc". These inputs
// feed prices, tax rates, shipping and collab compensation, so an ambiguous
// value has to be refused and shown back to the user rather than coerced.

/** The amount as a Number, or `null` when the text is not an unambiguous
 *  non-negative amount with at most two decimal places.
 *
 *  A single comma with no dot is read as a decimal separator ("12,50"), which
 *  is what a European keyboard produces. Anything else containing a comma
 *  (thousands grouping, mixed separators) is ambiguous and refused. */
export function parseMoney(input: string): number | null {
  if (typeof input !== 'string') return null
  const s = input.trim()
  if (!s) return null
  const commas = (s.match(/,/g) ?? []).length
  const normalized = !s.includes('.') && commas === 1 ? s.replace(',', '.') : s
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) return null
  return Number(normalized)
}

/** `parseMoney` in integer cents, or `null` on a value it refuses. */
export function parseMoneyCents(input: string): number | null {
  const n = parseMoney(input)
  return n === null ? null : Math.round(n * 100)
}
