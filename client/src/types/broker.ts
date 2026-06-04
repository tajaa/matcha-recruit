// --- Employee Benefits: eligibility exceptions ---

export type BenefitExceptionType = 'new_hire_enrollment_gap' | 'termination_premium_leak'

export interface EligibilityException {
  id: string
  company_id: string
  company_name: string
  employee_name: string
  exception_type: BenefitExceptionType
  reference_date: string
  days_elapsed: number
  days_remaining: number | null
  estimated_monthly_leak: number | null
  status: 'open' | 'resolved' | 'dismissed'
  source: 'finch' | 'csv' | 'mock'
  last_nudge_sent_at: string | null
  detected_at: string
}

export interface EligibilityExceptionsSummary {
  new_hire_count: number
  termination_leak_count: number
  total_open: number
  estimated_monthly_leak: number
}

export interface EligibilityExceptionsResponse {
  summary: EligibilityExceptionsSummary
  exceptions: EligibilityException[]
}

// --- Employee Benefits: renewal risk radar ---

export type RenewalRiskBand = 'stable' | 'elevated' | 'critical'

export interface RenewalRadarSummary {
  client_count: number
  stable: number
  elevated: number
  critical: number
}

export interface RenewalRadarCompany {
  company_id: string
  company_name: string
  industry: string | null
  risk_band: RenewalRiskBand
  policy_month: number | null
  turnover_pct: number
  turnover_delta_pct: number
  lost_workdays: number
  near_misses: number
  behavioral_incidents: number
  headcount: number
  top_trigger: string | null
  computed_at: string
}

export interface RenewalRadarResponse {
  summary: RenewalRadarSummary
  companies: RenewalRadarCompany[]
}

export interface RenewalRiskDimension {
  dimension_type: 'company' | 'department' | 'location'
  dimension_value: string
  risk_band: RenewalRiskBand
  turnover_pct: number
  turnover_baseline_pct: number
  turnover_delta_pct: number
  lost_workdays: number
  lost_workdays_delta_pct: number
  near_misses: number
  behavioral_incidents: number
  headcount: number
  gross_payroll: number | null
  triggers: string[]
}

export interface RenewalRadarDetail {
  company_id: string
  company_name: string
  risk_band: RenewalRiskBand
  policy_month: number | null
  recommendation: string
  dimensions: RenewalRiskDimension[]
}

// --- Risk-trend alerts ---

export type BrokerRiskMetricKey =
  | 'trir'
  | 'dart'
  | 'lost_days'
  | 'claim_free_broken'
  | 'premium_increase'
  | 'behavioral_friction'

export interface BrokerRiskAlert {
  id: string
  company_id: string
  company_name: string
  metric_key: BrokerRiskMetricKey
  severity: 'warning' | 'critical'
  current_value: number | null
  prior_value: number | null
  delta_pct: number | null
  message: string
  is_read: boolean
  first_alerted_at: string | null
  last_alerted_at: string | null
  resolved_at: string | null
}

export interface BrokerRiskAlertsResponse {
  alerts: BrokerRiskAlert[]
  active_unread: number
}

// --- Portfolio reporting ---

export interface BrokerPortfolioSummary {
  total_linked_companies: number
  active_link_count: number
  pending_setup_count: number
  expired_setup_count: number
  healthy_companies: number
  at_risk_companies: number
  average_policy_compliance_rate: number
  open_action_item_total: number
  total_pre_term_checks?: number
  avg_portfolio_override_rate?: number
}

export interface BrokerCompanyMetric {
  company_id: string
  company_name: string
  link_status: string
  setup_status: string
  policy_compliance_rate: number
  open_action_items: number
  active_employee_count: number
  risk_signal: 'healthy' | 'at_risk' | 'watch'
  pre_term_checks?: number
  avg_separation_risk?: number
  separation_override_rate?: number
}

export interface BrokerPortfolioResponse {
  summary: BrokerPortfolioSummary
  setup_status_counts: Record<string, number>
  companies: BrokerCompanyMetric[]
}

// --- Referred clients ---

export interface BrokerReferredClient {
  company_id: string
  company_name: string
  industry: string
  company_size: string
  company_status: string
  link_status: string
  linked_at: string
  activated_at?: string
  active_employee_count: number
  enabled_feature_count: number
}

export interface BrokerReferredClientsResponse {
  broker_slug: string
  total: number
  clients: BrokerReferredClient[]
}

// --- Handbook coverage ---

export interface BrokerHandbookCoverage {
  handbook_id: string
  handbook_title: string
  company_id: string
  company_name: string
  strength_score: number
  strength_label: 'Strong' | 'Moderate' | 'Weak'
  total_sections: number
  state_count: number
  missing_section_count: number
}

// --- Client setups ---

export interface BrokerClientSetup {
  id: string
  company_name: string
  status: 'draft' | 'invited' | 'activated' | 'expired' | 'cancelled'
  contact_name: string
  contact_email: string
  headcount_hint: number
  invited_at?: string
  activated_at?: string
  created_at: string
  notes?: string
  locations?: { city: string; state: string; type: string }[]
  onboarding_stage?: 'submitted' | 'under_review' | 'configuring' | 'live'
}

export interface BrokerBatchCreateResponse {
  status: string
  count: number
  setups: BrokerClientSetup[]
  errors: { index: number; company_name: string; error: string }[]
}

export interface BrokerClientSetupsResponse {
  setups: BrokerClientSetup[]
  total: number
  expired_count: number
}

// --- Lite referral tokens ---

export interface BrokerLiteReferralToken {
  id: string
  broker_id: string
  token: string
  label: string | null
  created_at: string
  expires_at: string | null
  is_active: boolean
  use_count: number
  last_used_at: string | null
  referral_url: string
  payer: 'broker' | 'business'
}

export interface BrokerLiteReferralTokenListResponse {
  tokens: BrokerLiteReferralToken[]
  total: number
}

// --- Per-client detail ---

export interface BrokerClientCompany {
  id: string
  name: string
  industry: string | null
  size: string | null
  status: string
  link_status: string
  setup_status: string
  onboarding_stage: string | null
  active_employee_count: number
  policy_compliance_rate: number
  open_action_items: number
  risk_signal: 'healthy' | 'watch' | 'at_risk'
}

export interface BrokerClientLocation {
  id: string
  name: string | null
  city: string
  state: string
  total_requirements: number
  categories: Record<string, number>
}

export interface BrokerClientPolicyItem {
  id: string
  title: string
  category: string | null
  status: string
  pending_count: number
  signed_count: number
  total_count: number
  signature_rate: number
}

export interface BrokerClientDetailResponse {
  company: BrokerClientCompany
  compliance: {
    locations: BrokerClientLocation[]
    total_locations: number
    total_requirements: number
  }
  policies: {
    total_active: number
    compliance_rate: number
    items: BrokerClientPolicyItem[]
  }
  ir_summary: {
    total_open: number
    by_severity: Record<string, number>
    recent_30_days: number
  }
  er_summary: {
    total_open: number
    by_status: Record<string, number>
  }
  handbooks: BrokerHandbookCoverage[]
  recent_activity: {
    action: string
    timestamp: string
    source: string
  }[]
}

// --- WC portfolio (per-client TRIR / DART / premium) ---
// Shape returned by GET /broker/wc-portfolio. Merged into the Book of Business
// table by company_id. Previously inlined in BrokerWcPortfolio.tsx.

export type WcSeverityBand = 'good' | 'fair' | 'at_risk' | 'critical' | 'unknown'

export interface WcBenchmark {
  sector: string
  label: string
  trir: number
  dart: number
}

export interface WcPremiumImpact {
  base_premium_estimate: number
  mod_swing: number
  annual_impact_dollars: number
  direction: 'increase' | 'decrease' | 'neutral'
}

export interface WcPortfolioRow {
  company_id: string
  company_name: string
  industry: string | null
  headcount: number | null
  recordable_cases: number
  dart_cases: number
  lost_days: number
  trir: number | null
  dart_rate: number | null
  days_since_last_recordable: number | null
  trir_delta_pct: number | null
  benchmark: WcBenchmark | null
  premium_impact: WcPremiumImpact | null
  severity_band: WcSeverityBand
  data_quality: { insufficient_population: boolean; headcount_missing: boolean }
}

export interface WcPortfolioSummary {
  client_count: number
  critical: number
  at_risk: number
  fair: number
  good: number
  unknown: number
  total_recordable_cases: number
  total_lost_days: number
}

export interface WcPortfolioResponse {
  summary: WcPortfolioSummary
  companies: WcPortfolioRow[]
}

// --- Action Center: positive milestones ---

export type MilestoneFamily = 'incident_free' | 'dart_free' | 'trir_below_benchmark'

export interface BrokerMilestone {
  id: string
  company_id: string
  company_name: string
  milestone_key: string
  milestone_family: MilestoneFamily
  tier: number | null
  title: string
  detail: string | null
  current_value: number | null
  benchmark_value: number | null
  is_read: boolean
  achieved_at: string
  superseded_at: string | null
}

export interface BrokerMilestonesResponse {
  summary: { total: number; unread: number }
  milestones: BrokerMilestone[]
}

// --- Action Center: AI consultative outreach ---

export type OutreachTone = 'celebratory' | 'advisory' | 'urgent'

export interface OutreachPrompt {
  title: string
  rationale: string
  suggested_action: string
  resource_link: string | null
  tone: OutreachTone
}

export interface OutreachResponse {
  company_id: string
  company_name: string
  cached: boolean
  prompts: OutreachPrompt[]
  generated_at: string | null
  model: string | null
}
