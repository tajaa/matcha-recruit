// Locally-defined compliance API types, shared across the split domain modules.

// ── Compliance Calendar ──

export interface ComplianceCalendarItem {
  id: string
  location_id: string | null
  location_name: string | null
  location_state: string | null
  jurisdiction_name: string | null
  requirement_id: string | null
  title: string
  category: string | null
  severity: string
  deadline: string  // ISO date
  derived_status: 'overdue' | 'due_soon' | 'upcoming' | 'future'
  days_until_due: number
  action_required: string | null
  alert_status: string  // 'unread' | 'read' | 'actioned' | 'dismissed' | 'baseline'
  created_at: string
}

// ── Certifications & Licenses (per-company, joined to catalog) ──

export interface CompanyCredential {
  id: string
  catalog_id: string
  slug: string
  name: string
  issuing_authority: string | null
  scope_level: string
  industry_tag: string | null
  renewal_months: number | null
  description: string | null
  source_url: string | null
  location_id: string | null   // null → company-wide
  source: string
  status: string
  added_at: string | null
}

// ── Pending Research ──

export type PendingResearch = {
  coverage_requests: {
    city: string
    state: string
    county: string | null
    note: string | null
    requested_at: string | null
  }[]
  vertical: { label: string; areas: number; in_review?: number } | null
}

// ── Quality Audit Types ──

export interface QualityRequirement {
  id: string
  jurisdiction_id: string
  category: string
  title: string | null
  description: string | null
  source_url: string | null
  source_url_status?: 'unchecked' | 'ok' | 'dead' | null
  source_tier: string | null
  current_value: string | null
  effective_date: string | null
  last_verified_at: string | null
  is_bookmarked: boolean
  created_at: string
  updated_at: string
  jurisdiction_name: string
  state: string
  city: string
  completeness_score: number
  staleness_days: number | null
  research_source: string | null
  statute_citation?: string | null
  citation_verified?: boolean
  change_status?: string | null
}

export interface QualityAuditSummary {
  total: number
  avg_completeness: number
  stale_count: number
  missing_source_url: number
  dead_source_url?: number
  verified_citation?: number
  unverified_citation?: number
  gemini_unverified?: number
  needs_review?: number
  tier_breakdown: Record<string, number>
  provenance_breakdown: Record<string, number>
}

export interface QualityAuditResponse {
  summary: QualityAuditSummary
  requirements: QualityRequirement[]
}

export interface CoverageCell {
  req_count: number
  best_tier: number
  avg_completeness: number
  max_staleness_days: number | null
}

export interface CoverageMatrixResponse {
  jurisdictions: Array<{ id: string; name: string; state: string; city: string }>
  categories: string[]
  cells: Record<string, CoverageCell>
}

// ── Regulatory Q&A ──

export interface RegulatoryQASource {
  requirement_id: string
  title: string
  category: string
  jurisdiction_name: string
  jurisdiction_level: string
  source_url: string | null
  source_name: string | null
  statute_citation: string | null
  similarity: number
}

export interface RegulatoryQAResponse {
  answer: string
  sources: RegulatoryQASource[]
  confidence: number
}

// ── Payer Medical Policy Navigator ──

export interface PayerPolicySource {
  policy_id: string
  payer_name: string
  policy_title: string | null
  policy_number: string | null
  procedure_description: string | null
  coverage_status: string
  source_url: string | null
  source_document: string | null
  similarity: number
}

export interface PayerPolicyQAResponse {
  answer: string
  sources: PayerPolicySource[]
  confidence: number
}

export interface PayerPolicy {
  id: string
  payer_name: string
  payer_type: string | null
  policy_number: string | null
  policy_title: string | null
  procedure_codes: string[]
  procedure_description: string | null
  coverage_status: string
  requires_prior_auth: boolean
  clinical_criteria: string | null
  documentation_requirements: string | null
  medical_necessity_criteria: string | null
  age_restrictions: string | null
  frequency_limits: string | null
  source_url: string | null
  source_document: string | null
  effective_date: string | null
  last_reviewed: string | null
}

// ── Protocol Gap Analysis ──

export interface ProtocolAnalysisItem {
  requirement_key: string
  title: string
  status: 'covered' | 'gap' | 'partial'
  evidence?: string
  guidance?: string
  missing?: string
}

export interface ProtocolAnalysisResult {
  covered: ProtocolAnalysisItem[]
  gaps: ProtocolAnalysisItem[]
  partial: ProtocolAnalysisItem[]
  summary: string
  requirements_analyzed: number
}

// ── Policy Drafting ──

export interface PolicyDraftCitation {
  requirement_key: string
  title: string
  source_url: string
}

export interface PolicyDraftResult {
  title: string
  content: string
  citations: PolicyDraftCitation[]
  applicable_jurisdictions: string[]
  category: string
}

// ── Key Coverage & Integrity (Admin) ──

export interface RegulationKeyCoverage {
  id: string
  key: string
  name: string
  enforcing_agency: string | null
  base_weight: number
  state_variance: string
  key_group: string | null
  status: 'present' | 'missing'
  jurisdiction_count: number
  best_tier: number
  days_since_verified: number | null
  staleness_level: 'fresh' | 'warning' | 'critical' | 'expired' | 'no_data'
  newest_value: string | null
}

export interface PartialGroup {
  group: string
  present: number
  expected: number
  missing: string[]
}

export interface CategoryKeyCoverage {
  category: string
  group: string
  label: string
  expected: number
  present: number
  coverage_pct: number
  weighted_score: number
  keys: RegulationKeyCoverage[]
  partial_groups: PartialGroup[]
}

export interface KeyCoverageResponse {
  summary: {
    total_defined_keys: number
    total_present: number
    key_coverage_pct: number
    weighted_score: number
    categories_fully_covered: number
    categories_with_gaps: number
    stale_warning: number
    stale_critical: number
  }
  by_category: CategoryKeyCoverage[]
}

export interface IntegrityCheckResponse {
  missing_keys: Array<{
    jurisdiction_id: string
    city: string
    state: string
    key: string
    category: string
    key_name: string
    key_group: string | null
    weight: number
  }>
  missing_count: number
  orphaned_records: Array<{
    id: string
    jurisdiction_id: string
    city: string
    state: string
    category: string
    regulation_key: string
    title: string
    source_tier: string
  }>
  orphaned_count: number
  stale_keys: Array<{
    id: string
    city: string
    state: string
    category: string
    regulation_key: string
    key_name: string
    days_since_verified: number
    staleness_level: 'warning' | 'critical' | 'expired'
  }>
  stale_count: number
  partial_groups: Array<{
    key_group: string
    category: string
    city: string
    state: string
    present: number
    expected: number
    coverage_pct: number
    missing: string[]
  }>
  partial_group_count: number
  total_defined_keys: number
  total_db_records: number
  linked_records: number
  integrity_score: number
}

// ── Payer Policy Admin ──

export interface PayerOverviewResponse {
  total: number
  payer_count: number
  coverage: { covered: number; conditional: number; not_covered: number }
  sources: { cms: number; gemini: number }
  field_completeness: { clinical_criteria_pct: number; procedure_codes_pct: number; source_url_pct: number }
  staleness: { warning: number; critical: number }
  last_ingest: string | null
  by_payer: Array<{ payer: string; count: number; covered: number; conditional: number }>
}

export interface PayerIntegrityResponse {
  stale_policies: Array<{ id: string; payer: string; policy_number: string; title: string; coverage_status: string; days_since_verified: number; level: string }>
  stale_count: number
  missing_fields: Array<{ id: string; payer: string; policy_number: string; title: string; missing: string[] }>
  missing_fields_count: number
  low_confidence: Array<{ id: string; payer: string; policy_number: string; title: string; confidence: number }>
  low_confidence_count: number
  recent_changes: Array<{ id: string; payer: string; policy_number: string; title: string; field: string; old_value: string | null; new_value: string | null; source: string; changed_at: string | null }>
  recent_changes_count: number
}
