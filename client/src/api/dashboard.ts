import { api } from './client'
import type {
  DashboardStats,
  CredentialExpirationsResponse,
  UpcomingResponse,
  EscalatedQueryListResponse,
  EscalatedQueryDetail,
  DashboardFlagsResponse,
  WageGapDetailsResponse,
  EmployeeFlightRiskList,
  EmployeeFlightRisk,
  FlightRiskWidgetSummary,
} from '../types/dashboard'

export function fetchDashboardStats() {
  return api.get<DashboardStats>('/dashboard/stats')
}

export function fetchCredentialExpirations() {
  return api.get<CredentialExpirationsResponse>('/dashboard/credential-expirations')
}

export function fetchUpcoming(days = 90) {
  return api.get<UpcomingResponse>(`/dashboard/upcoming?days=${days}`)
}

export function fetchEscalatedQueries(status?: string, limit = 30, offset = 0) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return api.get<EscalatedQueryListResponse>(`/dashboard/escalated-queries?${params}`)
}

export function fetchEscalatedQueryDetail(id: string) {
  return api.get<EscalatedQueryDetail>(`/dashboard/escalated-queries/${id}`)
}

export function resolveEscalatedQuery(id: string, resolution_note: string) {
  return api.put(`/dashboard/escalated-queries/${id}/resolve`, { resolution_note })
}

export function dismissEscalatedQuery(id: string, reason?: string) {
  return api.put(`/dashboard/escalated-queries/${id}/dismiss`, { reason: reason || null })
}

export function updateEscalatedQueryStatus(id: string, status: 'in_review') {
  return api.put(`/dashboard/escalated-queries/${id}/status`, { status })
}

export function fetchDashboardFlags() {
  return api.get<DashboardFlagsResponse>('/dashboard/flags')
}

export function analyzeDashboardFlags() {
  return api.post<{ analyzed: number; is_ai: boolean; analyzed_at: string }>('/dashboard/flags/analyze')
}

export function fetchWageGapDetails() {
  return api.get<WageGapDetailsResponse>('/dashboard/wage-gap/details')
}

export function fetchFlightRiskSummary() {
  return api.get<FlightRiskWidgetSummary>('/flight-risk/summary')
}

export function fetchFlightRiskEmployees() {
  return api.get<EmployeeFlightRiskList>('/flight-risk/employees')
}

export function fetchFlightRiskEmployee(employeeId: string) {
  return api.get<EmployeeFlightRisk>(`/flight-risk/employees/${employeeId}`)
}

export function snapshotFlightRisk() {
  return api.post<{ snapshotted: number }>('/flight-risk/snapshot')
}

export async function downloadWageGapCsv() {
  // Auth is Bearer-token, not cookie, so a plain <a href> won't send creds.
  // Fetch as blob, build an object URL, click a synthetic <a download>.
  const token = localStorage.getItem('matcha_access_token')
  const base = import.meta.env.VITE_API_URL ?? '/api'
  const res = await fetch(`${base}/dashboard/wage-gap/export.csv`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error(`Export failed: ${res.status}`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `wage-gap-${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
