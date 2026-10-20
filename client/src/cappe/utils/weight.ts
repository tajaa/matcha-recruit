// Product and rate weights are stored in grams; owners type them in their
// store's unit — pounds where the store is based in a pound country, else
// kilograms. Parsing is as strict as money's (utils/money.ts): "1,5" is 1.5,
// "1.2.3" and "2lb" are refused rather than read as something else.
import { parseMoney } from './money'

export type WeightUnit = 'lb' | 'kg'

const POUND_COUNTRIES = new Set(['US', 'LR', 'MM'])
const GRAMS: Record<WeightUnit, number> = { lb: 453.59237, kg: 1000 }

export const weightUnit = (country?: string | null): WeightUnit =>
  POUND_COUNTRIES.has((country || '').toUpperCase()) ? 'lb' : 'kg'

/** Grams for the typed weight: `null` when blank, `undefined` when unreadable. */
export function gramsFromText(text: string, unit: WeightUnit): number | null | undefined {
  if (!text.trim()) return null
  const n = parseMoney(text, { maxDecimals: 3 })
  return n === null ? undefined : Math.round(n * GRAMS[unit])
}

/** The stored grams as the owner reads them (up to three decimals). */
export function textFromGrams(grams: number | null | undefined, unit: WeightUnit): string {
  if (grams == null) return ''
  return String(Math.round((grams / GRAMS[unit]) * 1000) / 1000)
}
