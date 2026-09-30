// One currency formatter for agent-card results (product prices and flight
// fares alike).

/** 310 or "310.00" + "USD" → "$310.00"; an unknown currency code falls back to
 *  "310.00 XYZ", and a string that isn't a number comes back as it was. */
export function formatMoney(amount: number | string | null | undefined, currency?: string | null): string {
  if (amount == null) return ''
  const value = Number(amount)
  if (!Number.isFinite(value)) return String(amount)
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: currency || 'USD' }).format(value)
  } catch {
    return `${value.toFixed(2)} ${currency}`
  }
}
