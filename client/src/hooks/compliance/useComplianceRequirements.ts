import { useMemo } from 'react'
import type { ComplianceRequirement } from '../../types/compliance'
import {
  CATEGORY_GROUPS, ALL_CATEGORY_KEYS, LABOR_CATEGORIES,
  type CategoryGroup,
} from '../../generated/complianceCategories'

type SectionId = CategoryGroup

const SECTION_ORDER: SectionId[] = ['labor', 'supplementary', 'healthcare', 'behavioral_health', 'oncology', 'medical_compliance', 'life_sciences', 'manufacturing']
const SECTION_LABELS: Record<SectionId, string> = {
  labor: 'Core Labor',
  supplementary: 'Supplementary',
  healthcare: 'Healthcare',
  behavioral_health: 'Behavioral Health',
  oncology: 'Oncology',
  medical_compliance: 'Medical Compliance',
  life_sciences: 'Life Sciences',
  manufacturing: 'Manufacturing',
}

const CATEGORY_ORDER_INDEX = new Map(ALL_CATEGORY_KEYS.map((k, i) => [k, i]))

// Top-down: the broadest floor first, the most local (and usually governing)
// rule last — the order a manager reads a jurisdiction stack in.
const LEVEL_ORDER = ['federal', 'state', 'county', 'city']

export function normalizeCategoryKey(category: string): string {
  return category.trim().toLowerCase().replace(/[\s-]+/g, '_')
}

function getSectionId(category: string): SectionId {
  return (CATEGORY_GROUPS as Record<string, SectionId>)[category] || 'supplementary'
}

export interface CategorySection {
  id: SectionId
  label: string
  categories: [string, ComplianceRequirement[]][]
  requirementCount: number
}

/** A jurisdiction the tenant's requirements come from — the "By jurisdiction"
 *  lens groups on the authority that issued each rule instead of its topic. */
export interface JurisdictionSection {
  id: string
  label: string
  level: string
  categories: [string, ComplianceRequirement[]][]
  requirementCount: number
}

/** Stable id for a jurisdiction section — also the prefix of its accordion keys.
 *  Exported because the same category repeats across jurisdictions in this lens,
 *  so expansion state (and the ask-source deep-link) must key per section. */
export function jurisdictionSectionId(level: string, name: string): string {
  return `${level || 'other'}:${name || 'Unknown'}`
}

export interface Authority { level: string; name: string }

// The federal government under the names the catalog actually writes. Naming the
// United States is a fact, not an inference — unlike anything else here, which is
// why this list stays exactly this: no state abbreviations, no city aliases.
const FEDERAL_ALIASES = new Set(['federal', 'united states', 'us', 'u.s.', 'usa'])

function normalizeLevel(level: string | null | undefined): string {
  const l = (level || '').trim().toLowerCase()
  // `national` is the catalog's other spelling of federal; left as-is it sorts
  // to the bottom as an unknown level, below the city rules it outranks.
  return l === 'national' ? 'federal' : l
}

/** Who issued this rule.
 *
 *  `authority_*` is resolved server-side through the catalog FK and is the
 *  trustworthy answer. `jurisdiction_level`/`jurisdiction_name` are free text
 *  written at materialization time and are wrong often enough to matter (one
 *  live tenant has federal rules labelled level "national" and a city ordinance
 *  labelled "state / _county_san francisco, CA"), so they are only the fallback
 *  — for the minority of rows with no catalog link, where nothing better exists.
 */
export function requirementAuthority(
  req: ComplianceRequirement,
  known?: Map<string, Authority>,
): Authority {
  if (req.authority_name) {
    return { level: normalizeLevel(req.authority_level), name: req.authority_name.trim() }
  }
  const name = req.jurisdiction_name?.trim() || 'Unknown'
  // No catalog link. Of the two free-text fields the LEVEL is the corrupt one
  // (a row reading "national / California" is CA state law), so let an exactly
  // matching name — the stronger signal — carry the level with it. Anything
  // short of an exact match keeps the row's own text: a near-miss is a guess,
  // and mis-parenting a rule under a jurisdiction it doesn't come from is worse
  // than an oddly-named section.
  const match = known?.get(name.toLowerCase())
  if (match) return match
  const level = normalizeLevel(req.jurisdiction_level)
  if (level === 'federal' && FEDERAL_ALIASES.has(name.toLowerCase())) {
    const federal = known?.get('federal')
    if (federal) return federal
  }
  return { level, name }
}

/** The authorities this tenant demonstrably has, keyed by lowercased name.
 *
 *  Built only from catalog-linked rows — it is the trusted set that rows with no
 *  link get resolved against (see `requirementAuthority`). Feed it the UNFILTERED
 *  requirements: what counts as a known authority must not change as the user
 *  types in the search box.
 */
export function useKnownAuthorities(requirements: ComplianceRequirement[] | undefined) {
  return useMemo(() => {
    const map = new Map<string, Authority>()
    for (const req of requirements ?? []) {
      if (!req.authority_name) continue
      const authority = { level: normalizeLevel(req.authority_level), name: req.authority_name.trim() }
      map.set(authority.name.toLowerCase(), authority)
      if (authority.level === 'federal') map.set('federal', authority)
    }
    return map
  }, [requirements])
}

export function useComplianceRequirements(
  requirements: ComplianceRequirement[] | undefined,
  /** The trusted authority set, from the unfiltered requirements. Omit and it is
   *  derived from `requirements` — correct only when those aren't a subset. */
  authorities?: Map<string, Authority>,
) {
  const derivedAuthorities = useKnownAuthorities(requirements)
  const knownAuthorities = authorities ?? derivedAuthorities

  const requirementsByCategory = useMemo(() => {
    if (!requirements) return {}
    return requirements.reduce((acc, req) => {
      const category = normalizeCategoryKey(req.category || 'other')
      if (!acc[category]) acc[category] = []
      acc[category].push({ ...req, category })
      return acc
    }, {} as Record<string, ComplianceRequirement[]>)
  }, [requirements])

  const orderedRequirementCategories = useMemo(() => {
    const categories = new Set(Object.keys(requirementsByCategory))
    LABOR_CATEGORIES.forEach((c: string) => categories.add(c))
    return Array.from(categories)
      .sort((a, b) => {
        const aIdx = CATEGORY_ORDER_INDEX.get(a)
        const bIdx = CATEGORY_ORDER_INDEX.get(b)
        if (aIdx !== undefined && bIdx !== undefined) return aIdx - bIdx
        if (aIdx !== undefined) return -1
        if (bIdx !== undefined) return 1
        return a.localeCompare(b)
      })
      .map((category) => [category, requirementsByCategory[category] || []] as [string, ComplianceRequirement[]])
  }, [requirementsByCategory])

  const sectionedCategories = useMemo(() => {
    const buckets = new Map<SectionId, [string, ComplianceRequirement[]][]>()
    for (const id of SECTION_ORDER) buckets.set(id, [])

    for (const entry of orderedRequirementCategories) {
      const [category, reqs] = entry
      const sectionId = getSectionId(category)
      if (reqs.length === 0) continue
      buckets.get(sectionId)?.push(entry)
    }

    const sections: CategorySection[] = []
    for (const id of SECTION_ORDER) {
      const categories = buckets.get(id)!
      if (categories.length === 0) continue
      sections.push({
        id,
        label: SECTION_LABELS[id],
        categories,
        requirementCount: categories.reduce((sum, [, reqs]) => sum + reqs.length, 0),
      })
    }
    return sections
  }, [orderedRequirementCategories])

  // "By jurisdiction" lens: one section per authority (Federal → California →
  // LA County → City of LA), category accordions inside. The topic sections
  // above answer "what subject is this?"; this answers "who is imposing it?" —
  // which is the question behind "does the city add anything on top of state?".
  const jurisdictionSections = useMemo(() => {
    if (!requirements) return []
    const buckets = new Map<string, { level: string; name: string; byCategory: Map<string, ComplianceRequirement[]> }>()

    for (const req of requirements) {
      const { level, name } = requirementAuthority(req, knownAuthorities)
      const id = jurisdictionSectionId(level, name)
      let bucket = buckets.get(id)
      if (!bucket) {
        bucket = { level, name, byCategory: new Map() }
        buckets.set(id, bucket)
      }
      const category = normalizeCategoryKey(req.category || 'other')
      const list = bucket.byCategory.get(category)
      if (list) list.push({ ...req, category })
      else bucket.byCategory.set(category, [{ ...req, category }])
    }

    const sections: JurisdictionSection[] = []
    for (const [id, bucket] of buckets) {
      const categories = Array.from(bucket.byCategory.entries()).sort((a, b) => {
        const aIdx = CATEGORY_ORDER_INDEX.get(a[0])
        const bIdx = CATEGORY_ORDER_INDEX.get(b[0])
        if (aIdx !== undefined && bIdx !== undefined) return aIdx - bIdx
        if (aIdx !== undefined) return -1
        if (bIdx !== undefined) return 1
        return a[0].localeCompare(b[0])
      })
      sections.push({
        id,
        label: bucket.name,
        level: bucket.level,
        categories,
        requirementCount: categories.reduce((sum, [, reqs]) => sum + reqs.length, 0),
      })
    }

    // Federal → state → county → city; an unrecognized level sorts last rather
    // than silently vanishing (the catalog's level vocabulary can grow).
    return sections.sort((a, b) => {
      const aIdx = LEVEL_ORDER.indexOf(a.level)
      const bIdx = LEVEL_ORDER.indexOf(b.level)
      if (aIdx !== bIdx) return (aIdx === -1 ? LEVEL_ORDER.length : aIdx) - (bIdx === -1 ? LEVEL_ORDER.length : bIdx)
      return a.label.localeCompare(b.label)
    })
  }, [requirements, knownAuthorities])

  return {
    requirementsByCategory,
    orderedRequirementCategories,
    sectionedCategories,
    jurisdictionSections,
    knownAuthorities,
  }
}
