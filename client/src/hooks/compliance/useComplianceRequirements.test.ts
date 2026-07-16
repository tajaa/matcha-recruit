import { describe, it, expect } from 'vitest'
import { requirementAuthority, jurisdictionSectionId, type Authority } from './useComplianceRequirements'
import type { ComplianceRequirement } from '../../types/compliance'

// The catalog-linked authorities of a real tenant (Sunset Smile Dental, LA).
const KNOWN: Map<string, Authority> = new Map([
  ['federal', { level: 'federal', name: 'Federal' }],
  ['california', { level: 'state', name: 'California' }],
  ['los angeles county, ca', { level: 'county', name: 'Los Angeles County, CA' }],
  ['los angeles, ca', { level: 'city', name: 'Los Angeles, CA' }],
])

function req(partial: Partial<ComplianceRequirement>): ComplianceRequirement {
  return { id: 'r1', category: 'minimum_wage', title: 't', ...partial } as ComplianceRequirement
}

describe('requirementAuthority', () => {
  it('prefers the catalog-resolved authority over the free-text columns', () => {
    // The exact corruption this exists for: a city ordinance whose free text
    // claims it is San Francisco state law.
    const r = req({
      authority_level: 'city',
      authority_name: 'Los Angeles, CA',
      jurisdiction_level: 'state',
      jurisdiction_name: '_county_san francisco, CA',
    })
    expect(requirementAuthority(r, KNOWN)).toEqual({ level: 'city', name: 'Los Angeles, CA' })
  })

  it('maps the catalog\'s "national" spelling onto federal', () => {
    // Left alone it sorts below the city rules it outranks, and renders raw
    // (JURISDICTION_LEVEL_LABELS has no such key).
    const r = req({ authority_level: 'national', authority_name: 'Federal' })
    expect(requirementAuthority(r, KNOWN).level).toBe('federal')
  })

  describe('rows with no catalog link', () => {
    it('lets an exactly matching name carry the level with it', () => {
      // Cal-COBRA arrives as level "national", name "California" — it is CA
      // state law, and the name is the only field worth trusting.
      const r = req({ jurisdiction_level: 'national', jurisdiction_name: 'California' })
      expect(requirementAuthority(r, KNOWN)).toEqual({ level: 'state', name: 'California' })
    })

    it('resolves the federal government under the names the catalog writes', () => {
      const r = req({ jurisdiction_level: 'national', jurisdiction_name: 'United States' })
      expect(requirementAuthority(r, KNOWN)).toEqual({ level: 'federal', name: 'Federal' })
    })

    it('keeps its own text rather than re-parenting on a near-miss', () => {
      // "Los Angeles" is not "Los Angeles, CA". Mis-parenting a rule under a
      // jurisdiction it does not come from is worse than an odd section name.
      const r = req({ jurisdiction_level: 'city', jurisdiction_name: 'Los Angeles' })
      expect(requirementAuthority(r, KNOWN)).toEqual({ level: 'city', name: 'Los Angeles' })
    })

    it('does not invent an authority when nothing is known', () => {
      const r = req({ jurisdiction_level: 'city', jurisdiction_name: 'Los Angeles' })
      expect(requirementAuthority(r)).toEqual({ level: 'city', name: 'Los Angeles' })
    })

    it('never leaves the name blank', () => {
      const r = req({ jurisdiction_level: 'state', jurisdiction_name: '' })
      expect(requirementAuthority(r, KNOWN).name).toBe('Unknown')
    })
  })

  it('agrees with the section id the jurisdiction lens groups on', () => {
    // The ask-source deep-link expands `${sectionId}::${cat}`; if these two ever
    // disagree the cited row's accordion silently stays shut.
    const r = req({ authority_level: 'city', authority_name: 'Los Angeles, CA' })
    const a = requirementAuthority(r, KNOWN)
    expect(jurisdictionSectionId(a.level, a.name)).toBe('city:Los Angeles, CA')
  })
})
