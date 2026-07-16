import { CATEGORY_LABELS } from '../generated/complianceCategories'
export { CATEGORY_LABELS }
export type { CategoryGroup } from '../generated/complianceCategories'

export interface JurisdictionOption {
  city: string
  state: string
  county: string | null
  has_local_ordinance: boolean
}

/** @deprecated Use JurisdictionOption */
export type Jurisdiction = JurisdictionOption

export interface FacilityAttributes {
  entity_type?: string | null
  payer_contracts?: string[] | null
  bed_count?: number | null
  teaching_hospital?: boolean | null
}

/**
 * Clinical-care entity types. Presence of one on any active location is what
 * makes the payer/protocol/policy compliance tabs relevant. A dental office,
 * pharmacy, or lab is `entity_type` too but does NOT get those tabs — the gate
 * is this explicit allowlist, not "has an entity_type" or "has payer_contracts"
 * (a dental office can carry payer contracts and still not need payer policies).
 */
export const CLINICAL_ENTITY_TYPES: ReadonlySet<string> = new Set([
  'fqhc',
  'hospital',
  'critical_access_hospital',
  'clinic',
  'nursing_facility',
  'behavioral_health',
  'ambulatory_surgery_center',
  'home_health',
  'hospice',
  'dialysis_center',
])

// ── Risk cockpit ──────────────────────────────────────────────────────────
export interface RiskPenalty {
  civil_min?: number | null
  civil_max?: number | null
  per_violation?: boolean | null
  annual_cap?: number | null
  enforcing_agency?: string | null
  summary?: string | null
}

export interface RiskIssue {
  id: string
  source: 'wage' | 'credential' | 'incident' | 'alert'
  severity: 'critical' | 'high' | 'moderate'
  title: string
  detail?: string | null
  employee_names: string[]
  location_label?: string | null
  penalty?: RiskPenalty | null
  statute_citation?: string | null
  recommendation?: string | null
  link?: string | null
  deadline?: string | null
  alert_id?: string | null
}

export interface RiskPosture {
  open_critical: number
  open_high: number
  open_moderate: number
  employees_affected: number
  exposure_min_usd: number
  exposure_max_usd: number
  exposure_unquantified_count: number
  next_deadline_days?: number | null
  next_deadline_label?: string | null
}

export interface RiskGetAhead {
  title: string
  kind: 'legislation' | 'deadline'
  effective_date?: string | null
  days_until?: number | null
  location_label?: string | null
}

export interface ComplianceRiskSummary {
  posture: RiskPosture
  issues: RiskIssue[]
  get_ahead: RiskGetAhead[]
  generated_at: string
}

export interface LocationCreate {
  name?: string
  address?: string
  city: string
  state: string
  county?: string
  zipcode?: string
  facility_attributes?: FacilityAttributes
  ein?: string
  naics?: string
  max_employees?: number
  annual_avg_employees?: number
}

export interface LocationUpdate {
  name?: string
  address?: string
  city?: string
  state?: string
  county?: string
  zipcode?: string
  is_active?: boolean
  ein?: string
  naics?: string
  max_employees?: number
  annual_avg_employees?: number
}

export interface BusinessLocation {
  id: string
  company_id: string
  name: string | null
  address: string | null
  city: string
  state: string
  county: string | null
  zipcode: string | null
  is_active: boolean
  auto_check_enabled: boolean
  auto_check_interval_days: number
  next_auto_check: string | null
  last_compliance_check: string | null
  requirements_count: number
  unread_alerts_count: number
  employee_count: number
  employee_names: string[]
  data_status: string
  coverage_status: string
  has_local_ordinance: boolean
  facility_attributes?: FacilityAttributes | null
  source?: 'manual' | 'employee_derived'
  ein: string | null
  naics: string | null
  max_employees: number | null
  annual_avg_employees: number | null
  created_at: string
}

export interface ComplianceRequirement {
  id: string
  category: string
  rate_type: string | null
  applicable_industries: string[]
  jurisdiction_level: 'federal' | 'state' | 'county' | 'city' | 'special_district' | 'regulatory_body'
  jurisdiction_name: string
  title: string
  description: string | null
  current_value: string | null
  numeric_value: number | null
  source_url: string | null
  /** Liveness of source_url: 'unchecked' | 'ok' | 'dead' (null = no catalog link). */
  source_url_status?: 'unchecked' | 'ok' | 'dead' | null
  /** The OPERATIVE statute for this row's value, verified against the authority's own text (null = not yet codified). */
  statute_citation?: string | null
  citation_verified_at?: string | null
  /** Higher-level authorities this row sits on top of rather than restates — e.g. the federal floor a state threshold must meet or exceed. */
  jurisdictional_basis?: Array<{
    citation: string
    item_id: string
    index_slug: string | null
    level: string
    relation: 'floor'
  }> | null
  source_name: string | null
  effective_date: string | null
  previous_value: string | null
  last_changed_at: string | null
  affected_employee_count: number | null
  affected_employee_names: string[]
  min_wage_violation_count: number | null
  is_pinned: boolean
}

export interface VerificationSource {
  url: string
  name: string
  type: 'official' | 'news' | 'blog' | 'other'
  snippet?: string
}

export interface ComplianceAlert {
  id: string
  location_id: string
  requirement_id: string | null
  alert_type: 'change' | 'new_requirement' | 'upcoming_legislation' | 'deadline_approaching' | null
  title: string
  message: string
  severity: 'info' | 'warning' | 'critical'
  status: 'unread' | 'read' | 'dismissed' | 'actioned'
  category: string | null
  action_required: string | null
  source_url: string | null
  source_name: string | null
  deadline: string | null
  confidence_score: number | null
  verification_sources: VerificationSource[] | null
  effective_date: string | null
  metadata: Record<string, unknown> | null
  impact_summary: string | null
  affected_employee_count: number | null
  created_at: string
  read_at: string | null
}

export interface ComplianceSummary {
  total_locations: number
  total_requirements: number
  unread_alerts: number
  critical_alerts: number
  recent_changes: {
    location: string
    category: string
    title: string
    old_value: string | null
    new_value: string
    changed_at: string
  }[]
  auto_check_locations: number
  upcoming_deadlines: {
    title: string
    effective_date: string
    days_until: number
    status: string
    category: string | null
    location: string
  }[]
}

export interface PinnedRequirement {
  id: string
  category: string
  jurisdiction_level: string
  jurisdiction_name: string
  title: string
  description: string | null
  current_value: string | null
  effective_date: string | null
  source_url: string | null
  is_pinned: boolean
  location_name: string | null
  city: string
  state: string
}

export interface CheckLogEntry {
  id: string
  location_id: string
  company_id: string
  check_type: 'manual' | 'scheduled' | 'proactive'
  status: 'running' | 'completed' | 'failed'
  started_at: string
  completed_at: string | null
  new_count: number
  updated_count: number
  alert_count: number
  error_message: string | null
}

export interface UpcomingLegislation {
  id: string
  location_id: string
  category: string | null
  title: string
  description: string | null
  current_status: 'proposed' | 'passed' | 'signed' | 'effective_soon' | 'effective' | 'dismissed'
  expected_effective_date: string | null
  impact_summary: string | null
  source_url: string | null
  source_name: string | null
  confidence: number | null
  days_until_effective: number | null
  affected_employee_count: number | null
  created_at: string
}

export interface AssignableUser {
  id: string
  name: string
  email: string
  role: 'client' | 'admin'
}

export interface ComplianceActionPlanUpdate {
  action_owner_id?: string | null
  next_action?: string | null
  action_due_date?: string | null
  recommended_playbook?: string | null
  estimated_financial_impact?: string | null
  mark_actioned?: boolean
}

export interface AvailablePoster {
  location_id: string
  location_name: string
  state: string
  template_id: string | null
  poster_type: string
  title: string
  description: string | null
  download_url: string | null
  status: 'available' | 'ordered' | 'not_available'
}

export interface PosterOrder {
  id: string
  location_id: string
  template_ids: string[]
  status: 'pending' | 'processing' | 'shipped' | 'delivered' | 'cancelled'
  created_at: string
}

// SSE event types for compliance check streaming

export interface SSEHeartbeat {
  type: 'heartbeat'
}

export interface SSEProgress {
  type: 'progress'
  message: string
  phase: string
  progress: number
  timestamp: string
}

export interface SSENewRequirement {
  type: 'new_requirement'
  requirement_id: string
  category: string
  title: string
  jurisdiction_level: string
  current_value: string
}

export interface SSEAlertGenerated {
  type: 'alert_generated'
  alert_id: string
  title: string
  severity: string
  message: string
}

export interface SSEError {
  type: 'error'
  message: string
}

export type ComplianceSSEEvent =
  | SSEHeartbeat
  | SSEProgress
  | SSENewRequirement
  | SSEAlertGenerated
  | SSEError

// Requirement categories

export const REQUIREMENT_CATEGORIES = [
  'minimum_wage',
  'overtime',
  'sick_leave',
  'family_leave',
  'anti_discrimination',
  'workplace_safety',
  'workers_comp',
  'tax_withholding',
  'pay_frequency',
  'meal_breaks',
  'rest_breaks',
  'final_pay',
  'posting_requirements',
  'pto',
  'fair_scheduling',
  'ban_the_box',
  'non_compete',
  'harassment_training',
  'data_privacy',
  'whistleblower',
  'accommodations',
  'other',
] as const

export type RequirementCategory = (typeof REQUIREMENT_CATEGORIES)[number]

// ── Hierarchical Compliance Response Types ───────────────────────────────
// ALL intelligence is computed server-side. These are display-only types.

export interface TriggerActivation {
  trigger_type: 'attribute' | 'entity_type' | 'requirement_active' | 'category_active' | 'none'
  trigger_key: string | null
  trigger_value: unknown | null
  matched: boolean
}

export interface JurisdictionLevelRequirement {
  id: string
  jurisdiction_level: string
  jurisdiction_name: string
  title: string
  description: string | null
  current_value: string | null
  numeric_value: number | null
  source_url: string | null
  /** Liveness of source_url: 'unchecked' | 'ok' | 'dead'. */
  source_url_status?: 'unchecked' | 'ok' | 'dead' | null
  statute_citation: string | null
  status: string
  canonical_key: string | null
  triggered_by: TriggerActivation[] | null
}

export interface PrecedenceInfo {
  precedence_type: 'floor' | 'ceiling' | 'supersede' | 'additive'
  reasoning_text: string | null
  legal_citation: string | null
  trigger_condition: Record<string, unknown> | null
}

export interface CategoryComplianceStack {
  category: string
  category_label: string
  domain: string | null
  authority_type: string | null
  governing_level: string
  governing_requirement: JurisdictionLevelRequirement
  precedence: PrecedenceInfo | null
  all_levels: JurisdictionLevelRequirement[]
  affected_employee_count: number | null
}

export interface HierarchicalComplianceResponse {
  location_id: string
  location_name: string
  city: string
  state: string
  facility_attributes: Record<string, unknown> | null
  categories: CategoryComplianceStack[]
  total_categories: number
  total_requirements: number
}

export const categoryLabel: Record<RequirementCategory, string> = {
  minimum_wage: 'Minimum Wage',
  overtime: 'Overtime',
  sick_leave: 'Sick Leave',
  family_leave: 'Family Leave',
  anti_discrimination: 'Anti-Discrimination',
  workplace_safety: 'Workplace Safety',
  workers_comp: "Workers' Comp",
  tax_withholding: 'Tax Withholding',
  pay_frequency: 'Pay Frequency',
  meal_breaks: 'Meal Breaks',
  rest_breaks: 'Rest Breaks',
  final_pay: 'Final Pay',
  posting_requirements: 'Posting Requirements',
  pto: 'PTO',
  fair_scheduling: 'Fair Scheduling',
  ban_the_box: 'Ban the Box',
  non_compete: 'Non-Compete',
  harassment_training: 'Harassment Training',
  data_privacy: 'Data Privacy',
  whistleblower: 'Whistleblower',
  accommodations: 'Accommodations',
  other: 'Other',
}
