import { api } from '../../client'
import type {
  ComplianceAlert,
  ComplianceActionPlanUpdate,
} from '../../../types/compliance'

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
