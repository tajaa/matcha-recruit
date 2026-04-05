import { api } from './client'
import type {
  DashboardStats,
  CredentialExpirationsResponse,
  UpcomingResponse,
  EscalatedQueryListResponse,
  EscalatedQueryDetail,
  DashboardFlagsResponse,
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

export function fetchDashboardFlags(refresh = false) {
  return api.get<DashboardFlagsResponse>(`/dashboard/flags${refresh ? '?refresh=true' : ''}`)
}
