import { api } from '../client'
import type {
  Shift, ShiftPayload, WeekResponse, ScheduleSummary,
  WeekTemplate, WeekTemplatePayload, TemplateBlock, BlockPayload, ScheduleRequest,
  AssignmentMovePayload, AssignmentMoveResponse,
  ScheduleJob, JobPayload, JobCredentialRequirement, RosterEmployee,
  AssignmentNotePayload, MealBreakWaiverAttestation,
} from '../../types/employeeSchedule'

// ---- Admin: shifts + weekly view ----

export function fetchWeek(weekStart: string, locationId: string) {
  return api.get<WeekResponse>(`/employee-schedule/week?start=${weekStart}&location=${locationId}`)
}

export function fetchRoster(locationId: string) {
  return api.get<{ employees: RosterEmployee[] }>(`/employee-schedule/roster?location=${locationId}`)
}

export function fetchJobs(locationId?: string) {
  const query = locationId ? `?location=${locationId}` : ''
  return api.get<{ jobs: ScheduleJob[] }>(`/employee-schedule/jobs${query}`)
}

export function createJob(payload: JobPayload) {
  return api.post<ScheduleJob>('/employee-schedule/jobs', payload)
}

export function updateJob(id: string, payload: JobPayload) {
  return api.put<ScheduleJob>(`/employee-schedule/jobs/${id}`, payload)
}

export function deleteJob(id: string) {
  return api.delete<{ ok: boolean; id: string }>(`/employee-schedule/jobs/${id}`)
}

export function replaceJobEmployees(jobId: string, employeeIds: string[]) {
  return api.put<{ job_id: string; employee_ids: string[] }>(
    `/employee-schedule/jobs/${jobId}/employees`, { employee_ids: employeeIds },
  )
}

export function replaceJobCredentialRequirements(jobId: string, requirements: JobCredentialRequirement[]) {
  return api.put<{ job_id: string; credential_requirements: JobCredentialRequirement[] }>(
    `/employee-schedule/jobs/${jobId}/credential-requirements`, { requirements },
  )
}

/** For a `?shift=` deep link (the Huume `[[shift:…]]` pill) that carries no
 *  location — resolves which location to scope the page to. */
export function fetchShift(shiftId: string) {
  return api.get<Shift>(`/employee-schedule/shifts/${shiftId}`)
}

export function updateAssignmentNote(shiftId: string, employeeId: string, payload: AssignmentNotePayload) {
  return api.put<Shift>(`/employee-schedule/shifts/${shiftId}/assignments/${employeeId}/note`, payload)
}

export function fetchMealBreakWaiver(employeeId: string) {
  return api.get<MealBreakWaiverAttestation>(`/employee-schedule/employees/${employeeId}/meal-break-waiver`)
}

export function updateMealBreakWaiver(
  employeeId: string,
  payload: { on_file: boolean; effective_from?: string | null; note?: string | null },
) {
  return api.put<MealBreakWaiverAttestation>(`/employee-schedule/employees/${employeeId}/meal-break-waiver`, payload)
}

export function createShift(payload: ShiftPayload, force = false) {
  return api.post<Shift>(`/employee-schedule/shifts${force ? '?force=true' : ''}`, payload)
}

/** True PATCH: send only the fields you're changing. An explicit null clears a
 *  nullable column (role, department, location_id, color, notes). `force`
 *  retimes past a double-booking conflict, same as createShift. */
export function updateShift(id: string, payload: Partial<ShiftPayload>, force = false) {
  return api.put<Shift>(`/employee-schedule/shifts/${id}${force ? '?force=true' : ''}`, payload)
}

/** `force` proceeds past a Fair Workweek notice/clopening advisory on a
 *  published shift — same force-through convention as create/update. */
export function deleteShift(id: string, force = false) {
  return api.delete<{ ok: boolean; id: string }>(
    `/employee-schedule/shifts/${id}${force ? '?force=true' : ''}`,
  )
}

export function publishShift(id: string) {
  return api.post<Shift>(`/employee-schedule/shifts/${id}/publish`, {})
}

export function publishRange(start: string, end: string, locationId?: string) {
  return api.post<{ published: number; shifts: Shift[]; summary: ScheduleSummary }>(
    '/employee-schedule/shifts/publish', { start, end, location_id: locationId || null },
  )
}

/** Bulk convention (same as generateFromTemplate): never a per-date 409 — a
 *  conflicting or unavailable assignee is dropped for that copy and named in
 *  `dropped`, the shift is still created as an open draft. */
export function duplicateShift(id: string, targetDates: string[], includeAssignments = true) {
  return api.post<{
    created: number
    shifts: Shift[]
    dropped: { date: string; employee_id: string; name: string; reason: string }[]
    compliance_warnings: { message: string }[]
  }>(`/employee-schedule/shifts/${id}/duplicate`,
     { target_dates: targetDates, include_assignments: includeAssignments })
}

// ---- Admin: assignments ----

export function assignEmployee(shiftId: string, employeeId: string, force = false) {
  return api.post<Shift>(
    `/employee-schedule/shifts/${shiftId}/assignments${force ? '?force=true' : ''}`,
    { employee_id: employeeId },
  )
}

export function unassignEmployee(shiftId: string, employeeId: string, force = false) {
  return api.delete<Shift>(
    `/employee-schedule/shifts/${shiftId}/assignments/${employeeId}${force ? '?force=true' : ''}`,
  )
}

export function moveAssignment(payload: AssignmentMovePayload, force = false) {
  return api.post<AssignmentMoveResponse>(
    `/employee-schedule/assignments/move${force ? '?force=true' : ''}`,
    payload,
  )
}

// ---- Admin: location scheduling-law panel ----

export interface ScheduleLawRules {
  source: 'curated' | 'catalog_extraction' | 'unmapped'
  [rule_key: string]: unknown
}

export interface ScheduleLawStatute {
  requirement_id: string
  state: string
  category: string
  title: string
  statute_citation: string | null
  source_url: string | null
}

export interface LocationComplianceResponse {
  state: string | null
  rules: ScheduleLawRules
  statutes: ScheduleLawStatute[]
}

export function fetchLocationCompliance(locationId: string) {
  return api.get<LocationComplianceResponse>(`/employee-schedule/compliance/location/${locationId}`)
}

// ---- Admin: week templates ----

export function fetchWeekTemplates(locationId: string) {
  return api.get<{ week_templates: WeekTemplate[] }>(`/employee-schedule/week-templates?location=${locationId}`)
}

export function createWeekTemplate(payload: WeekTemplatePayload) {
  return api.post<WeekTemplate>('/employee-schedule/week-templates', payload)
}

/** True PATCH on parent fields only — blocks are managed via their own endpoints. */
export function updateWeekTemplate(id: string, payload: Partial<WeekTemplatePayload>) {
  return api.put<WeekTemplate>(`/employee-schedule/week-templates/${id}`, payload)
}

export function deleteWeekTemplate(id: string) {
  return api.delete<{ ok: boolean; id: string }>(`/employee-schedule/week-templates/${id}`)
}

export function addTemplateBlock(weekTemplateId: string, payload: BlockPayload) {
  return api.post<TemplateBlock>(`/employee-schedule/week-templates/${weekTemplateId}/blocks`, payload)
}

/** True PATCH, like updateShift. */
export function updateTemplateBlock(weekTemplateId: string, blockId: string, payload: Partial<BlockPayload>) {
  return api.put<TemplateBlock>(`/employee-schedule/week-templates/${weekTemplateId}/blocks/${blockId}`, payload)
}

export function deleteTemplateBlock(weekTemplateId: string, blockId: string) {
  return api.delete<{ ok: boolean; id: string }>(`/employee-schedule/week-templates/${weekTemplateId}/blocks/${blockId}`)
}

export function generateFromWeekTemplate(weekTemplateId: string, startDate: string, endDate: string) {
  return api.post<{
    created: number; series_id: string; shifts: Shift[]
    compliance_warnings?: { check: string; severity: string; message: string; statute?: string | null }[]
  }>(
    `/employee-schedule/week-templates/${weekTemplateId}/generate`, { start_date: startDate, end_date: endDate },
  )
}

// ---- Admin: availability ----

export interface AvailabilityWindow { weekday: number; start_time: string; end_time: string }

export function fetchEmployeeAvailability(employeeId: string) {
  return api.get<{ windows: AvailabilityWindow[] }>(`/employee-schedule/availability/${employeeId}`)
}

export function saveEmployeeAvailability(employeeId: string, windows: AvailabilityWindow[]) {
  return api.put<{ saved: number }>(`/employee-schedule/availability/${employeeId}`, { windows })
}

// ---- Admin: request review ----

export function fetchRequests(status?: string) {
  const q = status ? `?status=${status}` : ''
  return api.get<{ requests: ScheduleRequest[] }>(`/employee-schedule/requests${q}`)
}

export function reviewRequest(id: string, decision: 'approved' | 'denied', reviewNotes?: string, force = false) {
  return api.post<ScheduleRequest>(`/employee-schedule/requests/${id}/review`, {
    decision, review_notes: reviewNotes ?? null, force,
  })
}

// ---- Schedule eligibility ----

export interface ScheduleEligibilityCase {
  id: string
  employee_id: string
  location_id: string | null
  location_name: string | null
  credential_label: string | null
  blocking_reason_code: string
  status: 'warning_open' | 'removal_requested' | 'removal_completed' | 'keep_acknowledged' | 'resolved'
  expires_at: string | null
  first_name: string
  last_name: string
  affected_assignment_count: number
  removed_assignment_count: number
  automatic_enforcement: boolean
}

export function fetchEligibilityCases(locationId?: string | null) {
  const q = locationId ? `?location_id=${encodeURIComponent(locationId)}` : ''
  return api.get<{ cases: ScheduleEligibilityCase[] }>(`/employee-schedule/eligibility-cases${q}`)
}

// ---- Employee portal ----

export function fetchMySchedule(start: string, end: string) {
  return api.get<{ shifts: Shift[] }>(
    `/v1/portal/me/schedule?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`,
  )
}

export function fetchMyRequests() {
  return api.get<{ requests: ScheduleRequest[] }>('/v1/portal/me/schedule/requests')
}

export function fetchMyOffers() {
  return api.get<{ offers: ScheduleRequest[] }>('/v1/portal/me/schedule/offers')
}

export function fetchMyCoworkers() {
  return api.get<{ employees: { id: string; name: string }[] }>('/v1/portal/me/schedule/coworkers')
}

export function acceptMyRequest(id: string, counterShiftId?: string | null) {
  return api.post<ScheduleRequest>(`/v1/portal/me/schedule/requests/${id}/accept`, {
    counter_shift_id: counterShiftId ?? null,
  })
}

export function withdrawMyRequest(id: string) {
  return api.post<{ status: string; request_id: string }>(`/v1/portal/me/schedule/requests/${id}/withdraw`, {})
}

export interface MyRequestPayload {
  request_type: 'swap' | 'drop' | 'pickup' | 'unavailable'
  shift_id?: string | null
  target_employee_id?: string | null
  unavailable_start?: string | null
  unavailable_end?: string | null
  reason?: string | null
}

export function createMyRequest(payload: MyRequestPayload) {
  return api.post<ScheduleRequest>('/v1/portal/me/schedule/requests', payload)
}

export function cancelMyRequest(id: string) {
  return api.delete<{ status: string; request_id: string }>(`/v1/portal/me/schedule/requests/${id}`)
}

export function fetchMyAvailability() {
  return api.get<{ windows: AvailabilityWindow[] }>('/v1/portal/me/schedule/availability')
}

export function saveMyAvailability(windows: AvailabilityWindow[]) {
  return api.put<{ saved: number }>('/v1/portal/me/schedule/availability', { windows })
}
