// Shared utilities for Jurisdiction Data admin page

import { CATEGORY_GROUPS } from '../../../generated/complianceCategories'
import type { SpecialtyFilter } from './types'

export function fmtDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })
}

export function matchesSpecialty(cat: string, filter: SpecialtyFilter): boolean {
  if (filter === 'all') return true
  const group = CATEGORY_GROUPS[cat]
  if (filter === 'healthcare') return group === 'healthcare' || group === 'oncology'
  if (filter === 'oncology') return group === 'oncology'
  if (filter === 'medical') return group === 'medical_compliance'
  if (filter === 'general') return group !== 'healthcare' && group !== 'oncology' && group !== 'medical_compliance'
  // Individual category key
  return cat === filter
}

const INDUSTRY_SPECIFIC_RATE_TYPES = ['tipped', 'hotel', 'fast_food', 'healthcare']

export function matchesProfileRateTypes(requirementKey: string, profileRateTypes: Set<string>): boolean {
  const specificType = INDUSTRY_SPECIFIC_RATE_TYPES.find(rt => requirementKey.includes(rt))
  if (!specificType) return true
  return profileRateTypes.has(specificType)
}
