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
