import type { RequirementPenalties } from './types'

// Compact penalty chip text: "≤ $10,000" from civil_penalty_max, else the
// summary truncated. Null when the block has nothing displayable.
export function penaltyChipText(p: RequirementPenalties | null | undefined): string | null {
  if (!p) return null
  const max = p.civil_penalty_max
  if (max !== null && max !== undefined && max !== '') {
    const n = typeof max === 'number' ? max : Number(max)
    return Number.isFinite(n) ? `≤ $${n.toLocaleString()}` : `≤ ${max}`
  }
  if (p.summary) return p.summary.length > 40 ? `${p.summary.slice(0, 40)}…` : p.summary
  return null
}
