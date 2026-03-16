import { api } from './client'
import type {
  Jurisdiction,
  BusinessLocation,
  ComplianceRequirement,
  ComplianceAlert,
  ComplianceSummary,
} from '../types/compliance'

export function fetchJurisdictions() {
  return api.get<Jurisdiction[]>('/compliance/jurisdictions')
}

export function fetchLocations() {
  return api.get<BusinessLocation[]>('/compliance/locations')
}

export function createLocation(data: {
  name?: string
  address?: string
  city: string
  state: string
  county?: string
  zipcode?: string
}) {
  return api.post<BusinessLocation>('/compliance/locations', data)
}

export function deleteLocation(id: string) {
  return api.delete(`/compliance/locations/${id}`)
}

export function fetchRequirements(locationId: string, category?: string) {
  const params = category ? `?category=${encodeURIComponent(category)}` : ''
  return api.get<ComplianceRequirement[]>(
    `/compliance/locations/${locationId}/requirements${params}`
  )
}

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

export function fetchSummary() {
  return api.get<ComplianceSummary>('/compliance/summary')
}

export function getComplianceCheckUrl(locationId: string): string {
  const base = import.meta.env.VITE_API_URL || '/api'
  return `${base}/compliance/locations/${locationId}/check`
}

export function pinRequirement(requirementId: string, isPinned: boolean) {
  return api.post(`/compliance/requirements/${requirementId}/pin`, {
    is_pinned: isPinned,
  })
}

export function fetchPinnedRequirements() {
  return api.get<ComplianceRequirement[]>('/compliance/pinned-requirements')
}
