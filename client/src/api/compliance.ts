import { api } from './client'
import type {
  JurisdictionOption,
  BusinessLocation,
  LocationCreate,
  LocationUpdate,
  FacilityAttributes,
  ComplianceRequirement,
  ComplianceAlert,
  ComplianceSummary,
  PinnedRequirement,
  CheckLogEntry,
  UpcomingLegislation,
  AssignableUser,
  ComplianceActionPlanUpdate,
  AvailablePoster,
  PosterOrder,
} from '../types/compliance'

// ── Jurisdictions ──

export function fetchJurisdictions() {
  return api.get<JurisdictionOption[]>('/compliance/jurisdictions')
}

// ── Locations ──

export function fetchLocations() {
  return api.get<BusinessLocation[]>('/compliance/locations')
}

export function fetchLocation(locationId: string) {
  return api.get<BusinessLocation>(`/compliance/locations/${locationId}`)
}

export function createLocation(data: LocationCreate) {
  return api.post<BusinessLocation>('/compliance/locations', data)
}

export function updateLocation(locationId: string, data: LocationUpdate) {
  return api.put<BusinessLocation>(`/compliance/locations/${locationId}`, data)
}

export function deleteLocation(id: string) {
  return api.delete(`/compliance/locations/${id}`)
}

// ── Facility Attributes ──

export function fetchFacilityAttributes(locationId: string) {
  return api.get<{ facility_attributes: FacilityAttributes }>(
    `/compliance/locations/${locationId}/facility-attributes`
  )
}

export function updateFacilityAttributes(locationId: string, data: Partial<FacilityAttributes>) {
  return api.patch<{ facility_attributes: FacilityAttributes }>(
    `/compliance/locations/${locationId}/facility-attributes`,
    data
  )
}

// ── Requirements ──

export function fetchRequirements(locationId: string, category?: string) {
  const params = category ? `?category=${encodeURIComponent(category)}` : ''
  return api.get<ComplianceRequirement[]>(
    `/compliance/locations/${locationId}/requirements${params}`
  )
}

export function pinRequirement(requirementId: string, isPinned: boolean) {
  return api.post(`/compliance/requirements/${requirementId}/pin`, {
    is_pinned: isPinned,
  })
}

export function fetchPinnedRequirements() {
  return api.get<PinnedRequirement[]>('/compliance/pinned-requirements')
}

// ── Alerts ──

export function fetchAlerts(status?: string, severity?: string, locationId?: string) {
  const parts: string[] = []
  if (status) parts.push(`status=${encodeURIComponent(status)}`)
  if (severity) parts.push(`severity=${encodeURIComponent(severity)}`)
  if (locationId) parts.push(`location_id=${encodeURIComponent(locationId)}`)
  const qs = parts.length ? `?${parts.join('&')}` : ''
  return api.get<ComplianceAlert[]>(`/compliance/alerts${qs}`)
}

export function markAlertRead(alertId: string) {
  return api.put(`/compliance/alerts/${alertId}/read`)
}

export function dismissAlert(alertId: string) {
  return api.put(`/compliance/alerts/${alertId}/dismiss`)
}

export function updateAlertActionPlan(alertId: string, data: ComplianceActionPlanUpdate) {
  return api.put(`/compliance/alerts/${alertId}/action-plan`, data)
}

// ── Summary & Dashboard ──

export function fetchSummary() {
  return api.get<ComplianceSummary>('/compliance/summary')
}

export function fetchComplianceDashboard(horizonDays = 90) {
  return api.get<import('../types/dashboard').ComplianceDashboard>(
    `/compliance/dashboard?horizon_days=${horizonDays}`
  )
}

// ── Compliance Checks ──

export function getComplianceCheckUrl(locationId: string): string {
  const base = import.meta.env.VITE_API_URL || '/api'
  return `${base}/compliance/locations/${locationId}/check`
}

export function fetchCheckLog(locationId: string, limit = 20) {
  return api.get<CheckLogEntry[]>(
    `/compliance/locations/${locationId}/check-log?limit=${limit}`
  )
}

// ── Upcoming Legislation ──

export function fetchUpcomingLegislation(locationId: string) {
  return api.get<UpcomingLegislation[]>(
    `/compliance/locations/${locationId}/upcoming-legislation`
  )
}

export function assignLegislation(
  legislationId: string,
  data: { location_id: string; action_owner_id?: string; action_due_date?: string }
) {
  return api.put<{ alert_id: string }>(
    `/compliance/legislation/${legislationId}/assign`,
    data
  )
}

// ── Users ──

export function fetchAssignableUsers() {
  return api.get<AssignableUser[]>('/compliance/assignable-users')
}

// ── Posters ──

export function fetchAvailablePosters() {
  return api.get<AvailablePoster[]>('/compliance/posters/available')
}

export function fetchPosterOrders() {
  return api.get<{ orders: PosterOrder[] }>('/compliance/posters/orders')
}

export function createPosterOrder(data: { location_id: string; template_ids: string[] }) {
  return api.post<PosterOrder>('/compliance/posters/orders', data)
}

// ── Label maps ──

export const JURISDICTION_LEVEL_LABELS: Record<string, string> = {
  federal: 'Federal',
  state: 'State',
  county: 'County',
  city: 'City',
}

export const RATE_TYPE_LABELS: Record<string, string> = {
  general: 'General',
  tipped: 'Tipped',
  exempt_salary: 'Exempt Salary',
  hotel: 'Hotel',
  fast_food: 'Fast Food',
  healthcare: 'Healthcare',
  large_employer: 'Large Employer',
  small_employer: 'Small Employer',
}

// ── Quality Audit Types ──

export interface QualityRequirement {
  id: string
  jurisdiction_id: string
  category: string
  title: string | null
  description: string | null
  source_url: string | null
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
}

export interface QualityAuditSummary {
  total: number
  avg_completeness: number
  stale_count: number
  missing_source_url: number
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

// ── Quality Audit API ──

export function fetchQualityAudit(params: {
  state?: string
  category?: string
  min_completeness?: number
  max_completeness?: number
  stale_only?: boolean
  tier?: string
  source?: string
  limit?: number
  offset?: number
}): Promise<QualityAuditResponse> {
  const searchParams = new URLSearchParams()
  if (params.state) searchParams.set('state', params.state)
  if (params.category) searchParams.set('category', params.category)
  if (params.min_completeness != null) searchParams.set('min_completeness', String(params.min_completeness))
  if (params.max_completeness != null) searchParams.set('max_completeness', String(params.max_completeness))
  if (params.stale_only) searchParams.set('stale_only', 'true')
  if (params.tier) searchParams.set('tier', params.tier)
  if (params.source) searchParams.set('source', params.source)
  if (params.limit != null) searchParams.set('limit', String(params.limit))
  if (params.offset != null) searchParams.set('offset', String(params.offset))

  const qs = searchParams.toString()
  return api.get<QualityAuditResponse>(`/admin/jurisdictions/quality-audit${qs ? '?' + qs : ''}`)
}

export function fetchCoverageMatrix(params: {
  state?: string
  domain?: string
} = {}): Promise<CoverageMatrixResponse> {
  const searchParams = new URLSearchParams()
  if (params.state) searchParams.set('state', params.state)
  if (params.domain) searchParams.set('domain', params.domain)

  const qs = searchParams.toString()
  return api.get<CoverageMatrixResponse>(`/admin/jurisdictions/coverage-matrix${qs ? '?' + qs : ''}`)
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

export function askRegulatoryQuestion(question: string, locationId?: string): Promise<RegulatoryQAResponse> {
  return api.post<RegulatoryQAResponse>('/compliance/ask', {
    question,
    location_id: locationId,
  })
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

export function askPayerPolicyQuestion(
  question: string,
  locationId?: string,
  payerName?: string,
): Promise<PayerPolicyQAResponse> {
  return api.post<PayerPolicyQAResponse>('/compliance/payer-policies/ask', {
    question,
    location_id: locationId,
    payer_name: payerName,
  })
}

export function fetchPayerPolicies(params: {
  payer_name?: string
  procedure_code?: string
  requires_prior_auth?: boolean
  coverage_status?: string
  limit?: number
  offset?: number
} = {}): Promise<PayerPolicy[]> {
  const searchParams = new URLSearchParams()
  if (params.payer_name) searchParams.set('payer_name', params.payer_name)
  if (params.procedure_code) searchParams.set('procedure_code', params.procedure_code)
  if (params.requires_prior_auth !== undefined) searchParams.set('requires_prior_auth', String(params.requires_prior_auth))
  if (params.coverage_status) searchParams.set('coverage_status', params.coverage_status)
  if (params.limit) searchParams.set('limit', String(params.limit))
  if (params.offset) searchParams.set('offset', String(params.offset))
  const qs = searchParams.toString()
  return api.get<PayerPolicy[]>(`/compliance/payer-policies${qs ? '?' + qs : ''}`)
}

export function researchPayerPolicy(payerName: string, procedure: string): Promise<PayerPolicy> {
  return api.post<PayerPolicy>('/compliance/payer-policies/research', {
    payer_name: payerName,
    procedure,
  })
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

export function analyzeProtocol(
  protocolText: string,
  locationId?: string,
  categories?: string[],
): Promise<ProtocolAnalysisResult> {
  return api.post<ProtocolAnalysisResult>('/compliance/protocol-analysis', {
    protocol_text: protocolText,
    location_id: locationId,
    categories,
  })
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

export function draftPolicy(
  topic: string,
  jurisdiction: string,
  locationId?: string,
  industryContext?: string,
): Promise<PolicyDraftResult> {
  return api.post<PolicyDraftResult>('/policies/draft', {
    topic,
    jurisdiction,
    location_id: locationId,
    industry_context: industryContext,
  })
}

// ── Key Coverage & Integrity (Admin) ──

export interface RegulationKeyCoverage {
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
  partial_groups: PartialGroup[]
  partial_group_count: number
  total_defined_keys: number
  total_db_records: number
  linked_records: number
  integrity_score: number
}

export function fetchKeyCoverage(params?: {
  jurisdiction_id?: string
  category?: string
  state?: string
  gaps_only?: boolean
}) {
  const parts: string[] = []
  if (params?.jurisdiction_id) parts.push(`jurisdiction_id=${params.jurisdiction_id}`)
  if (params?.category) parts.push(`category=${encodeURIComponent(params.category)}`)
  if (params?.state) parts.push(`state=${encodeURIComponent(params.state)}`)
  if (params?.gaps_only) parts.push('gaps_only=true')
  const qs = parts.length ? `?${parts.join('&')}` : ''
  return api.get<KeyCoverageResponse>(`/admin/jurisdictions/key-coverage${qs}`)
}

export function fetchIntegrityCheck(params?: {
  jurisdiction_id?: string
  state?: string
}) {
  const parts: string[] = []
  if (params?.jurisdiction_id) parts.push(`jurisdiction_id=${params.jurisdiction_id}`)
  if (params?.state) parts.push(`state=${encodeURIComponent(params.state)}`)
  const qs = parts.length ? `?${parts.join('&')}` : ''
  return api.get<IntegrityCheckResponse>(`/admin/jurisdictions/integrity-check${qs}`)
}

export function runStalenessCheck(params?: {
  jurisdiction_id?: string
  state?: string
}) {
  return api.post<{
    alerts_created: number
    alerts_resolved: number
    stale_found: number
    missing_found: number
  }>('/admin/jurisdictions/run-staleness-check', params || {})
}
