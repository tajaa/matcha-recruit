// Strict money parsing for owner-facing amount inputs.
//
// `parseFloat` is wrong for money twice over: it truncates at the first
// non-numeric character, so "12.5.7" silently becomes 12.5 and "1,299" becomes
// 1 — a $1,299 product saved as $1.00 — and it accepts "12abc". These inputs
// feed prices, tax rates, shipping and collab compensation, so an ambiguous
// value has to be refused and shown back to the user rather than coerced.

type ParseOptions = {
  /** Accept a leading "-" (a signed price delta, e.g. "Small: -0.50"). */
  allowNegative?: boolean
  /** Decimal places accepted. Money is 2; a percentage rate needs 3 (8.875%). */
  maxDecimals?: number
}

/** The amount as a Number, or `null` when the text is not an unambiguous
 *  amount. Non-negative with at most two decimal places unless `opts` says
 *  otherwise — the strict default is the right one for a price, and each looser
 *  use has to ask for it by name.
 *
 *  A single comma with no dot is read as a decimal separator ("12,50"), which
 *  is what a European keyboard produces. Anything else containing a comma
 *  (thousands grouping, mixed separators) is ambiguous and refused. */
export function parseMoney(input: string, opts: ParseOptions = {}): number | null {
  if (typeof input !== 'string') return null
  const s = input.trim()
  if (!s) return null
  const { allowNegative = false, maxDecimals = 2 } = opts
  const commas = (s.match(/,/g) ?? []).length
  const normalized = !s.includes('.') && commas === 1 ? s.replace(',', '.') : s
  const pattern = new RegExp(`^${allowNegative ? '-?' : ''}\\d+(\\.\\d{1,${maxDecimals}})?$`)
  if (!pattern.test(normalized)) return null
  return Number(normalized)
}

/** `parseMoney` in integer cents, or `null` on a value it refuses. */
export function parseMoneyCents(input: string, opts: ParseOptions = {}): number | null {
  const n = parseMoney(input, opts)
  return n === null ? null : Math.round(n * 100)
}

/** A signed option price delta in cents ("-0.50" → -50). The server stores
 *  `price_delta_cents` signed — a smaller size can cost less — so refusing a
 *  minus sign made every discounting option unsaveable. */
export function parseSignedMoneyCents(input: string): number | null {
  return parseMoneyCents(input, { allowNegative: true })
}

/** A percentage rate in basis points ("8.875" → 888). Rates carry three
 *  decimals in the wild (NYC sales tax is 8.875%); the server stores whole
 *  basis points, so the third decimal rounds to the nearest bp exactly as it
 *  did before this parser existed. */
export function parsePercentBps(input: string): number | null {
  const n = parseMoney(input, { maxDecimals: 3 })
  return n === null ? null : Math.round(n * 100)
}
