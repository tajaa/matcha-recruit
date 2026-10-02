import { api } from '../../api/client'
import type { HrCase, HrCaseColumn, HrCaseEmployee, HrCaseIncident, HrCaseReadiness, ManagerCase, DraftSubmission } from '../types'

// HR cases — the dedicated HR Cases page (business /work only).
// Backend: server/app/matcha/routes/matcha_work/hr_cases.py. Every route is
// HR-only server-side; a non-HR caller gets 404, never a partial list.

const BASE = '/matcha-work/hr-cases'

export const getHrCaseAccess = () => api.get<{ hr_access: boolean }>(`${BASE}/access`)

export const getHrCaseReadiness = () => api.get<HrCaseReadiness>(`${BASE}/readiness`)

export const listHrCases = (includeClosed = false) =>
  api.get<{ columns: HrCaseColumn[]; cases: HrCase[] }>(`${BASE}${includeClosed ? '?include_closed=true' : ''}`)

export const getHrCase = (caseId: string) => api.get<HrCase>(`${BASE}/${caseId}`)

export const dismissHrCase = (caseId: string, reason: string) =>
  api.post<HrCase>(`${BASE}/${caseId}/dismiss`, { reason })

// Manager side — the server returns only the manager's view of a case.
export const listMyWriteUps = () => api.get<{ cases: ManagerCase[] }>(`${BASE}/mine`)

export const searchCaseEmployees = (q: string) =>
  api.get<{ employees: HrCaseEmployee[] }>(`${BASE}/employees?${new URLSearchParams({ q })}`)

export const searchCaseIncidents = (q: string) =>
  api.get<{ incidents: HrCaseIncident[] }>(`${BASE}/incidents?${new URLSearchParams({ q })}`)

export function submitWriteUp(d: DraftSubmission) {
  const form = new FormData()
  form.append('employee_id', d.employeeId)
  form.append('action_type', d.actionType)
  form.append('infraction_type', d.infractionType)
  form.append('occurrence_dates', d.occurrenceDates.join(','))
  if (d.caseId) form.append('case_id', d.caseId)
  if (d.incidentId) form.append('incident_id', d.incidentId)
  if (d.file) form.append('file', d.file)
  if (d.googleUrl) form.append('google_url', d.googleUrl)
  if (d.driveFileId) form.append('drive_file_id', d.driveFileId)
  return api.upload<{ status: 'submitted' | 'held'; case: ManagerCase }>(`${BASE}/drafts`, form)
}

export const markWriteUpDelivered = (caseId: string, deliveredOn?: string) =>
  api.post<ManagerCase | HrCase>(`${BASE}/${caseId}/delivered`, deliveredOn ? { delivered_on: deliveredOn } : {})

export const getWriteUpDraftUrl = (caseId: string) =>
  api.get<{ url: string; filename: string; expires_in: number }>(`${BASE}/${caseId}/draft`)

// HR side.
export const decideHrCase = (caseId: string, decision: 'approve' | 'request_changes', reason?: string) =>
  api.post<HrCase>(`${BASE}/${caseId}/decision`, { decision, reason: reason || null })

// Signed copy — the manager or HR uploads; the check runs after the response.
export function uploadSignedCopy(caseId: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return api.upload<ManagerCase | HrCase>(`${BASE}/${caseId}/signed`, form)
}

export const getSignedCopyUrl = (caseId: string) =>
  api.get<{ url: string; filename: string; expires_in: number }>(`${BASE}/${caseId}/signed`)

export const acknowledgeHrCase = (caseId: string) => api.post<HrCase>(`${BASE}/${caseId}/acknowledge`)

export const recheckHrCase = (caseId: string) => api.post<HrCase>(`${BASE}/${caseId}/recheck`)
