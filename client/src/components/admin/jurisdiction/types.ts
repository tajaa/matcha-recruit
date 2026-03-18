// Shared types for Jurisdiction Data admin page

export type SpecialtyFilter = string

export type CityEntry = {
  id: string
  city: string
  categories_present: string[]
  categories_missing: string[]
  tier_breakdown: Record<string, number>
  last_verified_at: string | null
  is_stale: boolean
}

export type StateEntry = {
  state: string
  city_count: number
  coverage_pct: number
  cities: CityEntry[]
}

export type PreemptionRule = {
  state: string
  category: string
  allows_local_override: boolean
  notes: string | null
}

export type StructuredSource = {
  source_name: string
  source_type: string
  categories: string[]
  record_count: number
  last_fetched_at: string | null
  last_fetch_status: string | null
  is_active: boolean
}

export type DataOverview = {
  summary: {
    total_states: number
    total_cities: number
    total_requirements: number
    category_coverage_pct: number
    tier1_pct: number
    tier_breakdown: Record<string, number>
    stale_count: number
    freshness: { '7d': number; '30d': number; '90d': number; stale: number }
    required_categories: string[]
  }
  states: StateEntry[]
  preemption_rules: PreemptionRule[]
  structured_sources: StructuredSource[]
}

export type BookmarkedReq = {
  id: string
  category: string
  jurisdiction_level: string
  title: string
  current_value: string | null
  effective_date: string | null
  city: string
  state: string
  description: string | null
  previous_value: string | null
  last_verified_at: string | null
  jurisdiction_id: string
  source_url: string | null
  source_name: string | null
}

export type FlatCity = CityEntry & {
  stateName: string
  coveragePct: number
  gapCount: number
  presentCount: number
  totalCount: number
}

export type CatCoverage = {
  category: string
  label: string
  shortLabel: string
  count: number
  total: number
  pct: number
}

export type IndustryProfile = {
  id: string
  name: string
  description: string | null
  focused_categories: string[]
  rate_types: string[]
  category_order: string[]
  category_evidence: Record<string, { confidence: number; reason: string }> | null
  created_at: string | null
  updated_at: string | null
}

// ── Policy Browser types ────────────────────────────────────────────────────

export type PolicyCategorySummary = {
  slug: string
  name: string
  group: string
  requirement_count: number
  jurisdiction_count: number
  tier_breakdown: { tier_1_government: number; tier_2_official_secondary: number; tier_3_aggregator: number }
  latest_verified: string | null
}

export type PolicyDomainSummary = {
  domain: string
  label: string
  category_count: number
  requirement_count: number
  categories: PolicyCategorySummary[]
}

export type PolicyOverview = {
  summary: {
    total_requirements: number
    total_categories_with_data: number
    total_domains: number
    total_jurisdictions: number
  }
  domains: PolicyDomainSummary[]
}

export type PolicyRequirementDetail = {
  id: string
  jurisdiction_name: string
  jurisdiction_level: string
  state: string
  city: string | null
  title: string
  current_value: string | null
  numeric_value: number | null
  source_tier: string
  status: string
  statute_citation: string | null
  effective_date: string | null
  last_verified_at: string | null
}

export type PolicyCategoryDetail = {
  category: { slug: string; name: string; domain: string; group: string }
  requirements: PolicyRequirementDetail[]
}
