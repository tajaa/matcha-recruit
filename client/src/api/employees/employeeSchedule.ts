import { api } from '../client'
import type {
  Shift, ShiftPayload, WeekResponse, ScheduleSummary,
  ShiftTemplate, TemplatePayload, ScheduleRequest,
} from '../../types/employeeSchedule'

// ---- Admin: shifts + weekly view ----

export function fetchWeek(weekStart: string) {
  return api.get<WeekResponse>(`/employee-schedule/week?start=${weekStart}`)
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

export function publishRange(start: string, end: string) {
  return api.post<{ published: number; shifts: Shift[]; summary: ScheduleSummary }>(
    '/employee-schedule/shifts/publish', { start, end },
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

// ---- Admin: templates ----

export function fetchTemplates() {
  return api.get<{ templates: ShiftTemplate[] }>('/employee-schedule/templates')
}

export function createTemplate(payload: TemplatePayload) {
  return api.post<ShiftTemplate>('/employee-schedule/templates', payload)
}

/** True PATCH, like updateShift. */
export function updateTemplate(id: string, payload: Partial<TemplatePayload>) {
  return api.put<ShiftTemplate>(`/employee-schedule/templates/${id}`, payload)
}

export function deleteTemplate(id: string) {
  return api.delete<{ ok: boolean; id: string }>(`/employee-schedule/templates/${id}`)
}

export function generateFromTemplate(id: string, startDate: string, endDate: string) {
  return api.post<{
    created: number; series_id: string; shifts: Shift[]
    compliance_warnings?: { check: string; severity: string; message: string; statute?: string | null }[]
  }>(
    `/employee-schedule/templates/${id}/generate`, { start_date: startDate, end_date: endDate },
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

// ---- Employee portal ----

export function fetchMySchedule(start: string, end: string) {
  return api.get<{ shifts: Shift[] }>(
    `/v1/portal/me/schedule?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`,
  )
}

export function fetchMyRequests() {
  return api.get<{ requests: ScheduleRequest[] }>('/v1/portal/me/schedule/requests')
}

export interface MyRequestPayload {
  request_type: 'swap' | 'drop' | 'unavailable'
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
