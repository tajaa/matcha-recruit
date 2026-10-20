// The delivery-options editor's rows and how they become the API's
// (server: services/shipping.py). Pure, so the editor and the shipping card
// share one reading of what was typed.
import { parseMoneyCents } from './money'
import { gramsFromText, textFromGrams, type WeightUnit } from './weight'
import type { CappeShippingMethod, CappeShippingRateInput } from '../types'

export type RateRow = {
  key: number
  name: string
  method: CappeShippingMethod
  amount: string
  perItem: string
  freeOver: string
  minSubtotal: string
  maxSubtotal: string
  minWeight: string
  maxWeight: string
  minDays: string
  maxDays: string
  /** Comma- or space-separated postal codes (prefixes). */
  postal: string
  instructions: string
}

export const MAX_RATES = 10

let nextKey = 0
const money = (cents: number | null | undefined) => (cents == null ? '' : (cents / 100).toString())
const whole = (n: number | null | undefined) => (n == null ? '' : String(n))

export const METHODS: { value: CappeShippingMethod; label: string; name: string }[] = [
  { value: 'ship', label: 'Shipped', name: 'Standard' },
  { value: 'pickup', label: 'Pickup', name: 'Pickup' },
  { value: 'local_delivery', label: 'Local delivery', name: 'Local delivery' },
]

export function rateRow(r: CappeShippingRateInput, unit: WeightUnit): RateRow {
  return {
    key: nextKey++, name: r.name, method: r.method, amount: money(r.amount_cents),
    perItem: r.per_item_cents ? money(r.per_item_cents) : '', freeOver: money(r.free_over_cents),
    minSubtotal: money(r.min_subtotal_cents), maxSubtotal: money(r.max_subtotal_cents),
    minWeight: textFromGrams(r.min_weight_g, unit), maxWeight: textFromGrams(r.max_weight_g, unit),
    minDays: whole(r.delivery_min_days), maxDays: whole(r.delivery_max_days),
    postal: (r.postal_codes || []).join(', '), instructions: r.instructions || '',
  }
}

export function newRateRow(method: CappeShippingMethod = 'ship'): RateRow {
  return {
    key: nextKey++, name: METHODS.find((m) => m.value === method)?.name || 'Standard', method,
    amount: '', perItem: '', freeOver: '', minSubtotal: '', maxSubtotal: '', minWeight: '', maxWeight: '',
    minDays: '', maxDays: '', postal: '', instructions: '',
  }
}

/** The rows as the API takes them, or why they can't be saved. */
export function rateBodies(rows: RateRow[], unit: WeightUnit): CappeShippingRateInput[] | string {
  const out: CappeShippingRateInput[] = []
  for (const r of rows) {
    const name = r.name.trim()
    if (!name) return 'Give every delivery option a name.'
    const cents = (text: string, what: string): number | null | string => {
      if (!text.trim()) return null
      const c = parseMoneyCents(text)
      return c === null ? `Enter the ${what} for “${name}” as a plain amount, e.g. 5 or 5.50` : c
    }
    const days = (text: string): number | null | string => {
      if (!text.trim()) return null
      const n = Number(text)
      return Number.isInteger(n) && n >= 0 && n <= 90 ? n : `Enter the delivery time for “${name}” in whole days (0–90).`
    }
    const grams = (text: string): number | null | string => {
      const g = gramsFromText(text, unit)
      return g === undefined ? `Enter the weight limits for “${name}” in ${unit}, e.g. 2 or 2.5` : g
    }
    const values = {
      amount: cents(r.amount, 'price'), perItem: cents(r.perItem, 'extra-item price'),
      freeOver: cents(r.freeOver, 'free-over amount'), minSubtotal: cents(r.minSubtotal, 'order-value limit'),
      maxSubtotal: cents(r.maxSubtotal, 'order-value limit'), minWeight: grams(r.minWeight),
      maxWeight: grams(r.maxWeight), minDays: days(r.minDays), maxDays: days(r.maxDays),
    }
    const problem = Object.values(values).find((v) => typeof v === 'string')
    if (typeof problem === 'string') return problem
    const v = values as Record<keyof typeof values, number | null>
    for (const [low, high, what] of [
      [v.minSubtotal, v.maxSubtotal, 'order value'], [v.minWeight, v.maxWeight, 'weight'], [v.minDays, v.maxDays, 'delivery time'],
    ] as const) {
      if (low != null && high != null && low > high) return `“${name}”: the lowest ${what} is above the highest.`
    }
    const postal = r.method === 'local_delivery'
      ? r.postal.split(/[\s,;]+/).map((p) => p.trim().toUpperCase()).filter(Boolean)
      : []
    out.push({
      name, method: r.method, amount_cents: v.amount ?? 0,
      per_item_cents: r.method === 'pickup' ? 0 : v.perItem ?? 0,
      free_over_cents: v.freeOver, min_subtotal_cents: v.minSubtotal, max_subtotal_cents: v.maxSubtotal,
      min_weight_g: v.minWeight, max_weight_g: v.maxWeight, delivery_min_days: v.minDays, delivery_max_days: v.maxDays,
      postal_codes: postal, instructions: r.method === 'pickup' ? r.instructions.trim() || null : null,
    })
  }
  return out
}
