// Lengths in the document's units: points, picas, inches, millimetres,
// centimetres or CSS pixels. A typed length may name its own unit ("3in",
// "12p6" for 12 picas 6 points, "40mm") or be a sum ("12+6").

import type { Units } from './types'

export const PT_PER: Record<Units, number> = { pt: 1, pc: 12, in: 72, mm: 72 / 25.4, cm: 72 / 2.54, px: 0.75 }
export const UNIT_LABEL: Record<Units, string> = { pt: 'Points', pc: 'Picas', in: 'Inches', mm: 'Millimetres',
  cm: 'Centimetres', px: 'Pixels' }
const PLACES: Record<Units, number> = { pt: 2, pc: 2, in: 3, mm: 2, cm: 3, px: 1 }

/** Points shown in `units`. */
export function show(pt: number, units: Units): string {
  if (units === 'pc') {
    const sign = pt < 0 ? '-' : ''
    const a = Math.abs(pt)
    const picas = Math.floor(a / 12 + 1e-9)
    const points = Math.round((a - picas * 12) * 100) / 100
    return `${sign}${picas}p${points}`
  }
  const k = 10 ** PLACES[units]
  return String(Math.round((pt / PT_PER[units]) * k) / k)
}

const TERM = /^\s*(-?\d*\.?\d+)\s*(p\s*(\d*\.?\d+)?|pt|pc|in|"|mm|cm|px)?\s*$/i

/** A typed length in points, or null. A bare number is in `units`. */
export function parse(text: string, units: Units): number | null {
  const parts = text.replace(/−/g, '-').split(/(?=[+-])|(?<=[+-])/).map((s) => s.trim()).filter(Boolean)
  let total = 0
  let sign = 1
  let any = false
  for (const part of parts) {
    if (part === '+') { sign = 1; continue }
    if (part === '-') { sign = -1; continue }
    const m = TERM.exec(part)
    if (!m) return null
    const n = Number(m[1])
    const u = (m[2] || '').toLowerCase().replace(/\s+/g, '')
    let pt: number
    if (u.startsWith('p') && u !== 'pt' && u !== 'pc' && u !== 'px') pt = n * 12 + (m[3] ? Number(m[3]) : 0)
    else if (u === '"' || u === 'in') pt = n * 72
    else if (u) pt = n * PT_PER[u as Units]
    else pt = n * PT_PER[units]
    total += sign * pt
    sign = 1
    any = true
  }
  return any ? total : null
}
