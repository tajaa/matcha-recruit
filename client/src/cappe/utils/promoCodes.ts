// The promo-code form on the Shop page, and turning it into an API body.
import { parseMoneyCents } from './money'
import type { CappePromoCode, CappePromoCodeInput } from '../types'

export type Form = {
  code: string; kind: 'percent' | 'fixed'; value: string; minimum: string
  starts: string; ends: string; cap: string; once: boolean; active: boolean
}

export const EMPTY: Form = { code: '', kind: 'percent', value: '', minimum: '', starts: '', ends: '', cap: '', once: false, active: true }
export function toForm(c: CappePromoCode): Form {
  return {
    code: c.code, kind: c.kind,
    value: c.kind === 'percent' ? String(c.percent_off ?? '') : ((c.amount_off_cents ?? 0) / 100).toString(),
    minimum: c.min_subtotal_cents ? (c.min_subtotal_cents / 100).toString() : '',
    starts: c.starts_on ?? '', ends: c.ends_on ?? '', cap: c.max_redemptions ? String(c.max_redemptions) : '',
    once: c.once_per_customer, active: c.active,
  }
}

/** The form as the API body, or the reason it can't be sent. */
export function toBody(f: Form): CappePromoCodeInput | string {
  const code = f.code.trim().toUpperCase()
  if (!/^[A-Z0-9][A-Z0-9_-]{2,39}$/.test(code)) return 'Use 3–40 letters, numbers, dashes or underscores, e.g. SUMMER10'
  let percent: number | null = null
  let amount: number | null = null
  if (f.kind === 'percent') {
    percent = Number(f.value)
    if (!Number.isInteger(percent) || percent < 1 || percent > 90) return 'Percent off must be a whole number from 1 to 90'
  } else {
    amount = parseMoneyCents(f.value)
    if (amount === null || amount <= 0) return 'Enter the amount off, e.g. 5 or 7.50'
  }
  const minimum = f.minimum.trim() === '' ? null : parseMoneyCents(f.minimum)
  if (f.minimum.trim() !== '' && minimum === null) return 'Enter the minimum spend as a plain amount, e.g. 50'
  const cap = f.cap.trim() === '' ? null : Number(f.cap)
  if (cap !== null && (!Number.isInteger(cap) || cap < 1)) return 'Total uses must be a whole number, 1 or more'
  if (f.starts && f.ends && f.ends < f.starts) return 'The end date must be on or after the start date'
  return {
    code, kind: f.kind, percent_off: percent, amount_off_cents: amount, min_subtotal_cents: minimum,
    starts_on: f.starts || null, ends_on: f.ends || null, max_redemptions: cap,
    once_per_customer: f.once, active: f.active,
  }
}
