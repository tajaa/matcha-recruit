import { useMemo } from 'react';
import type { ComplianceRequirement } from '../../api/compliance';

const REQUIREMENT_CATEGORY_ORDER = [
  'meal_breaks',
  'minimum_wage',
  'overtime',
  'pay_frequency',
  'sick_leave',
  'final_pay',
  'minor_work_permit',
  'scheduling_reporting',
  'workers_comp',
  'business_license',
  'tax_rate',
  'posting_requirements',
];

const CORE_REQUIREMENT_SECTIONS = [
  'meal_breaks',
  'minimum_wage',
  'overtime',
  'pay_frequency',
  'sick_leave',
  'final_pay',
  'minor_work_permit',
  'scheduling_reporting',
];

const INDUSTRY_SPECIFIC_CATEGORIES = new Set([
  'hipaa_privacy',
  'billing_integrity',
  'clinical_safety',
  'healthcare_workforce',
  'corporate_integrity',
  'research_consent',
  'state_licensing',
  'emergency_preparedness',
]);

function normalizeCategoryKey(category: string): string {
  return category.trim().toLowerCase().replace(/[\s-]+/g, '_');
}

function isIndustrySpecific(category: string, reqs: ComplianceRequirement[]): boolean {
  if (INDUSTRY_SPECIFIC_CATEGORIES.has(category)) return true;
  return reqs.some(r => r.applicable_industries && r.applicable_industries.length > 0);
}

export interface CategorySection {
  id: 'core_labor' | 'industry_specific';
  label: string;
  categories: [string, ComplianceRequirement[]][];
}

export function useComplianceRequirements(
  requirements: ComplianceRequirement[] | undefined,
  industryName?: string,
) {
  const requirementsByCategory = useMemo(() => {
    if (!requirements) return {};
    return requirements.reduce((acc, req) => {
      const category = normalizeCategoryKey(req.category || 'other');
      if (!acc[category]) acc[category] = [];
      acc[category].push({ ...req, category });
      return acc;
    }, {} as Record<string, ComplianceRequirement[]>);
  }, [requirements]);

  const orderedRequirementCategories = useMemo(() => {
    const orderIndex = new Map(REQUIREMENT_CATEGORY_ORDER.map((cat, idx) => [cat, idx]));
    const categories = new Set(Object.keys(requirementsByCategory));
    CORE_REQUIREMENT_SECTIONS.forEach(category => categories.add(category));

    return Array.from(categories)
      .sort((a, b) => {
        const aIdx = orderIndex.get(a);
        const bIdx = orderIndex.get(b);
        if (aIdx !== undefined && bIdx !== undefined) return aIdx - bIdx;
        if (aIdx !== undefined) return -1;
        if (bIdx !== undefined) return 1;
        return a.localeCompare(b);
      })
      .map((category) => [category, requirementsByCategory[category] || []] as [string, ComplianceRequirement[]]);
  }, [requirementsByCategory]);

  const sectionedCategories = useMemo(() => {
    const core: [string, ComplianceRequirement[]][] = [];
    const industry: [string, ComplianceRequirement[]][] = [];

    for (const entry of orderedRequirementCategories) {
      const [category, reqs] = entry;
      if (isIndustrySpecific(category, reqs)) {
        industry.push(entry);
      } else {
        core.push(entry);
      }
    }

    const sections: CategorySection[] = [
      { id: 'core_labor', label: 'Core Labor', categories: core },
    ];

    if (industry.length > 0) {
      const label = industryName ? `${industryName}-Specific` : 'Industry-Specific';
      sections.push({ id: 'industry_specific', label, categories: industry });
    }

    return sections;
  }, [orderedRequirementCategories, industryName]);

  return { requirementsByCategory, orderedRequirementCategories, sectionedCategories };
}
