import { api } from './client'
import type {
  AiAudit, BiometricPoint, PayTransparencyRow, PayTransparencyStatus, WorkforceSummary,
  CollectionType, ConsentMethod, PayEquityReview,
} from '../types/workforceCompliance'

// --- summary ---
export function fetchWorkforceSummary() {
  return api.get<WorkforceSummary>('/workforce-compliance/summary')
}

// --- AI hiring-tool audits ---
export function fetchAiAudits() {
  return api.get<AiAudit[]>('/workforce-compliance/ai-audits')
}
export function createAiAudit(payload: {
  tool_name: string; vendor?: string | null; purpose?: string | null
  last_audit_date?: string | null; cadence_days?: number; notes?: string | null
}) {
  return api.post<AiAudit>('/workforce-compliance/ai-audits', payload)
}
export function updateAiAudit(id: string, payload: Record<string, unknown>) {
  return api.put<AiAudit>(`/workforce-compliance/ai-audits/${id}`, payload)
}
export function deleteAiAudit(id: string) {
  return api.delete<{ status: string }>(`/workforce-compliance/ai-audits/${id}`)
}

// --- biometric consent points ---
export function fetchBiometricPoints() {
  return api.get<BiometricPoint[]>('/workforce-compliance/biometric-points')
}
export function createBiometricPoint(payload: {
  collection_type: CollectionType; purpose?: string | null; consent_obtained?: boolean
  consent_obtained_date?: string | null; consent_method?: ConsentMethod | null
  retention_policy?: string | null; notes?: string | null
}) {
  return api.post<BiometricPoint>('/workforce-compliance/biometric-points', payload)
}
export function updateBiometricPoint(id: string, payload: Record<string, unknown>) {
  return api.put<BiometricPoint>(`/workforce-compliance/biometric-points/${id}`, payload)
}
export function deleteBiometricPoint(id: string) {
  return api.delete<{ status: string }>(`/workforce-compliance/biometric-points/${id}`)
}

// --- pay-equity study register ---
export function fetchPayEquityReviews() {
  return api.get<PayEquityReview[]>('/workforce-compliance/pay-equity')
}
export function createPayEquityReview(payload: {
  review_date?: string | null; scope?: string | null; methodology?: string | null
  gap_pct?: number | null; remediation?: string | null; cadence_days?: number; notes?: string | null
}) {
  return api.post<PayEquityReview>('/workforce-compliance/pay-equity', payload)
}
export function updatePayEquityReview(id: string, payload: Record<string, unknown>) {
  return api.put<PayEquityReview>(`/workforce-compliance/pay-equity/${id}`, payload)
}
export function deletePayEquityReview(id: string) {
  return api.delete<{ status: string }>(`/workforce-compliance/pay-equity/${id}`)
}

// --- pay transparency ---
export function fetchPayTransparency() {
  return api.get<PayTransparencyRow[]>('/workforce-compliance/pay-transparency')
}
export function setPayTransparency(state: string, payload: {
  status: PayTransparencyStatus; postings_include_ranges: boolean; note?: string | null
}) {
  return api.put<PayTransparencyRow[]>(`/workforce-compliance/pay-transparency/${state}`, payload)
}
