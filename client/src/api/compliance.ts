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

export function fetchAlerts(status?: string, severity?: string) {
  const parts: string[] = []
  if (status) parts.push(`status=${encodeURIComponent(status)}`)
  if (severity) parts.push(`severity=${encodeURIComponent(severity)}`)
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
