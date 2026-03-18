import { api } from './client'
import type {
  DashboardStats,
  CredentialExpirationsResponse,
  UpcomingResponse,
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
