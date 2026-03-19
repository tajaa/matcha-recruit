import { useMemo } from 'react'
import type { ComplianceRequirement } from '../../types/compliance'
import {
  CATEGORY_GROUPS, ALL_CATEGORY_KEYS, LABOR_CATEGORIES,
  type CategoryGroup,
} from '../../generated/complianceCategories'

type SectionId = CategoryGroup

const SECTION_ORDER: SectionId[] = ['labor', 'supplementary', 'healthcare', 'oncology', 'medical_compliance']
const SECTION_LABELS: Record<SectionId, string> = {
  labor: 'Core Labor',
  supplementary: 'Supplementary',
  healthcare: 'Healthcare',
  oncology: 'Oncology',
  medical_compliance: 'Medical Compliance',
}

const CATEGORY_ORDER_INDEX = new Map(ALL_CATEGORY_KEYS.map((k, i) => [k, i]))

function normalizeCategoryKey(category: string): string {
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

export function useComplianceRequirements(requirements: ComplianceRequirement[] | undefined) {
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

  return { requirementsByCategory, orderedRequirementCategories, sectionedCategories }
}
