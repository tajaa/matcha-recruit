import type { RiskIndex } from './riskIndex'

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
  // qualitative risk-theme alerts use dynamic 'theme:*' keys
  | (string & {})

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
  // theme alerts only (null for quantitative trend alerts)
  kind?: string | null
  suggestion?: string | null
  location_name?: string | null
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

// WC claim-depth (wcdeep01): taxonomy, return-to-work, NCCI rate, experience mod.

export interface WcClaimBreakdown {
  cumulative_trauma: number
  acute: number
  unknown: number
}

export interface WcRtw {
  lost_time_cases: number
  open: number
  resolved: number
  avg_days_to_rtw: number | null
}

export interface WcStateRate {
  state: string
  loss_cost_change_pct: number
  effective_date: string | null
  trend: 'increase' | 'decrease' | 'flat'
  source: string | null
  note: string | null
}

export interface WcMod {
  id: string
  company_id: string
  policy_period_start: string | null
  policy_period_end: string | null
  experience_mod: number
  carrier: string | null
  annual_premium: number | null
  note: string | null
  source: 'manual' | 'worksheet'
  created_at: string | null
}

// Directional experience-mod proxy (auto from loss-runs + class payroll).
export interface WcModProxyPoint {
  valuation_date: string | null
  experience_mod: number
  actual_losses: number
  expected_losses: number
  periods: number
  source: 'proxy'
}
export interface WcModProxy {
  points: WcModProxyPoint[]
  expected_annual_losses: number
  basis: string
}

// Draft returned by the worksheet-parse endpoint (broker confirms before saving).
export interface WcModWorksheetDraft {
  fields: {
    experience_mod: number | null
    policy_period_start: string | null
    carrier: string | null
    expected_losses: number | null
    actual_losses: number | null
    state: string | null
  }
  available: boolean
  model: string
}

export interface WcClassCode {
  state: string
  class_code: string
  description: string
  base_rate: number | null
  source: string
}

export interface WcClassExposure {
  id: string
  class_code: string
  state: string
  description: string | null
  payroll: number | null
  headcount: number | null
  base_rate: number | null
  est_manual_premium: number | null
  note: string | null
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
  // WC depth (optional — older shapes/merges tolerate absence).
  claim_breakdown?: WcClaimBreakdown
  post_termination_cases?: number
  rtw?: WcRtw
  primary_state?: string | null
  state_rate?: WcStateRate | null
  latest_mod?: WcMod | null
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
  total_ct_cases?: number
  total_post_termination?: number
  total_open_lost_time?: number
  clients_in_rate_increase_states?: number
}

export interface WcPortfolioResponse {
  summary: WcPortfolioSummary
  companies: WcPortfolioRow[]
}

// Full per-client WC view — GET /broker/wc-portfolio/{company_id}

export interface WcMetrics {
  headcount: number | null
  recordable_cases: number
  dart_cases: number
  lost_days: number
  trir: number | null
  dart_rate: number | null
  days_since_last_recordable: number | null
  benchmark: WcBenchmark | null
  premium_impact: WcPremiumImpact | null
  severity_band: WcSeverityBand
  claim_breakdown: WcClaimBreakdown
  post_termination_cases: number
  rtw: WcRtw
  prior: {
    trir_delta_pct: number | null
    dart_delta_pct: number | null
    lost_days_delta_pct: number | null
  }
  data_quality: { insufficient_population: boolean; headcount_missing: boolean }
}

export interface WcStateEntry {
  state: string
  rate: WcStateRate | null
}

export interface WcClientDetailResponse {
  company_id: string
  company_name: string
  metrics: WcMetrics
  states: WcStateEntry[]
  primary_state: string | null
  mods: WcMod[]
  mod_proxy: WcModProxy
}

// --- EPL readiness (epldeep01) ---

export type EplBand = 'strong' | 'adequate' | 'developing' | 'exposed'
export type EplFactorStatus = 'strong' | 'partial' | 'gap'
export type EplAttestationStatus = 'in_place' | 'partial' | 'gap' | 'unknown'

export interface EplAttestation {
  item_key: string
  status: EplAttestationStatus
  note: string | null
  updated_at: string | null
}

export interface EplFactor {
  key: string
  label: string
  kind: 'derived' | 'attested'
  weight: number
  score: number
  status: EplFactorStatus
  contribution: number
  detail: string
  attestation: EplAttestation | null
}

export interface EplReadiness {
  company_id: string
  company_name?: string
  score: number
  band: EplBand
  derived_score: number
  attested_score: number
  derived_max?: number
  attested_max?: number
  factors: EplFactor[]
}

export interface EplTopGap {
  key: string
  label: string
  score: number
}

export interface EplPortfolioRow {
  company_id: string
  company_name: string
  industry: string | null
  score: number
  band: EplBand
  derived_score: number
  attested_score: number
  top_gap: EplTopGap | null
}

export interface EplPortfolioSummary {
  client_count: number
  strong: number
  adequate: number
  developing: number
  exposed: number
  avg_score: number
}

export interface EplPortfolioResponse {
  summary: EplPortfolioSummary
  companies: EplPortfolioRow[]
}

// --- Off-platform broker clients (Broker Pro) ---

// --- Broker property portfolio ---
export interface PropertyPortfolioRow {
  company_id: string
  company_name: string
  industry: string | null
  building_count: number
  tiv: number
  avg_cope_score: number | null
  worst_cope_grade: string | null
  itv_ratio: number | null
  under_insured: number
  worst_cat_tier: string | null
}

export interface PropertyPortfolioResponse {
  summary: { client_count: number; total_tiv: number; under_insured_clients: number; severe_cat_clients: number }
  companies: PropertyPortfolioRow[]
}

export interface ExternalClient {
  id: string
  broker_id: string
  name: string
  industry: string | null
  headcount: number | null
  primary_state: string | null
  note: string | null
  status: string
  created_at: string | null
}

// Client-intake submission state, derived from the intake-token ledger.
export type ExternalIntakeState = 'submitted' | 'pending' | 'not_sent'

export interface ExternalIntakeStatus {
  status: ExternalIntakeState
  is_submitted: boolean
  submitted_at: string | null
  pending_sent_at: string | null
  pending_expires_at: string | null
}

export interface ExternalClientRow extends ExternalClient {
  wc_severity_band: WcSeverityBand
  wc_trir: number | null
  wc_current_emr: number | null
  epl_score: number
  epl_band: EplBand
  risk_index: number | null
  risk_band: string | null
  intake_status: ExternalIntakeState
  intake_submitted_at: string | null
  property_building_count: number
  property_tiv: number | null
  property_cat_tier: string | null
}

// Broker-keyed property summary for an off-platform client.
export interface ExternalProperty {
  has_data: boolean
  building_count: number
  total_tiv: number | null
  worst_construction: string | null
  sprinklered_pct: number | null
  worst_cat_tier: string | null
  insured_to_value_pct: number | null
  carrier: string | null
  annual_premium: number | null
  period_label: string | null
}

export interface ExternalPropertyPayload {
  period_label: string | null
  building_count: number
  total_tiv: number | null
  worst_construction: string | null
  sprinklered_pct: number | null
  worst_cat_tier: string | null
  insured_to_value_pct: number | null
  carrier: string | null
  annual_premium: number | null
  note: string | null
}

export interface ExternalWc {
  has_data: boolean
  period_label: string | null
  headcount: number | null
  recordable_cases: number
  dart_cases: number
  lost_days: number
  trir: number | null
  dart_rate: number | null
  benchmark: WcBenchmark | null
  severity_band: WcSeverityBand
  premium_impact: WcPremiumImpact | null
  claim_breakdown: WcClaimBreakdown
  post_termination_cases: number
  rtw: WcRtw
  current_emr: number | null
  carrier: string | null
  annual_premium: number | null
  state_rate: WcStateRate | null
}

export interface ExternalEplFactor {
  key: string
  label: string
  kind: 'derived' | 'attested'
  weight: number
  score: number
  status: EplFactorStatus
  contribution: number
  attest_status: EplAttestationStatus
  note: string | null
}

export interface ExternalEpl {
  score: number
  band: EplBand
  factors: ExternalEplFactor[]
}

export interface ExternalClientDetail {
  client: ExternalClient
  wc: ExternalWc
  epl: ExternalEpl
  property: ExternalProperty
  risk_index: RiskIndex
  intake: ExternalIntakeStatus
}

// --- Submission packet / coverage-gap ---

export interface CoverageGapItem {
  line: string
  concern: string
  suggestion: string
}

export interface CoverageGap {
  summary: string
  gaps: CoverageGapItem[]
  actions: string[]
  model: string
  available: boolean
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

// --- Seat allocation: pool + company-pinned client invites ---

export type ClientInviteTier = 'matcha_lite' | 'matcha_x'
export type ClientInviteStatus = 'outstanding' | 'redeemed' | 'revoked'

export interface BrokerClientInvite {
  id: string
  company_name: string | null
  seat_count: number | null
  tier: ClientInviteTier
  status: ClientInviteStatus
  redeemed_company_id: string | null
  redeemed_company_name?: string | null
  employees_used?: number
  created_at: string | null
  expires_at: string | null
  is_active: boolean
  signup_url: string
}

export interface BrokerSeatsResponse {
  allocated: number
  committed: number
  remaining: number
  clients: BrokerClientInvite[]
}

export interface BrokerClientInviteListResponse {
  invites: BrokerClientInvite[]
  total: number
}

// --- Broker team members ---

export type BrokerMemberRole = 'owner' | 'admin' | 'member'

export interface BrokerMember {
  id: string
  user_id: string
  email: string
  role: BrokerMemberRole
  is_active: boolean
  last_login: string | null
  created_at: string | null
  is_self: boolean
}

export interface BrokerMemberListResponse {
  members: BrokerMember[]
  total: number
}

export interface BrokerMemberCreateResponse {
  status: string
  member: { user_id: string; name: string; email: string; role: string }
  generated_password: boolean
  password: string
  email_sent: boolean
}
