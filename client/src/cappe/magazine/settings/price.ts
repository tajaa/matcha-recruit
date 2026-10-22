/** A magazine's monthly price as the writer types it, in dollars. */

/** Dollars as typed → cents, or null for blank; NaN when it isn't $1–$1,000. */
export function priceCents(typed: string): number | null {
  const t = typed.trim().replace(/^\$/, '')
  if (!t) return null
  const cents = Math.round(Number(t) * 100)
  return Number.isFinite(cents) && cents >= 100 && cents <= 100_000 ? cents : NaN
}

/** $5 or $5.50 a month, as the paywall shows it. */
export function priceLabel(cents: number): string {
  return `$${cents % 100 ? (cents / 100).toFixed(2) : cents / 100}`
}
