import { api } from '../../client'
import type { ComplianceSummary } from '../../../types/compliance'
import type { PendingResearch } from './types'

// ── Summary & Dashboard ──

export function fetchSummary() {
  return api.get<ComplianceSummary>('/compliance/summary')
}

export function fetchRiskSummary() {
  return api.get<import('../../../types/compliance').ComplianceRiskSummary>('/compliance/risk-summary')
}

export function fetchRemediations(days = 90) {
  return api.get<import('../../../types/compliance').RemediationRecord[]>(`/compliance/remediations?days=${days}`)
}

export function dismissRemediation(issueKey: string, reason: string) {
  return api.post('/compliance/remediations/dismiss', { issue_key: issueKey, reason })
}

export function addRemediationNote(issueKey: string, note: string) {
  return api.post('/compliance/remediations/note', { issue_key: issueKey, note })
}

export function reopenRemediation(issueKey: string) {
  return api.post('/compliance/remediations/reopen', { issue_key: issueKey })
}

export function fetchPendingResearch() {
  return api.get<PendingResearch>('/compliance/pending-research')
}

export function fetchComplianceDashboard(horizonDays = 90) {
  return api.get<import('../../../types/dashboard').ComplianceDashboard>(
    `/compliance/dashboard?horizon_days=${horizonDays}`
  )
}
