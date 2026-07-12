import { api } from './client'
import type {
  Shift, ShiftPayload, WeekResponse, ScheduleSummary,
  ShiftTemplate, TemplatePayload, ScheduleRequest,
} from '../types/employeeSchedule'

// ---- Admin: shifts + weekly view ----

export function fetchWeek(weekStart: string) {
  return api.get<WeekResponse>(`/employee-schedule/week?start=${weekStart}`)
}

export function createShift(payload: ShiftPayload, force = false) {
  return api.post<Shift>(`/employee-schedule/shifts${force ? '?force=true' : ''}`, payload)
}

export function updateShift(id: string, payload: ShiftPayload) {
  return api.put<Shift>(`/employee-schedule/shifts/${id}`, payload)
}

export function deleteShift(id: string) {
  return api.delete<{ ok: boolean; id: string }>(`/employee-schedule/shifts/${id}`)
}

export function publishShift(id: string) {
  return api.post<Shift>(`/employee-schedule/shifts/${id}/publish`, {})
}

export function publishRange(start: string, end: string) {
  return api.post<{ published: number; shifts: Shift[]; summary: ScheduleSummary }>(
    '/employee-schedule/shifts/publish', { start, end },
  )
}

// ---- Admin: assignments ----

export function assignEmployee(shiftId: string, employeeId: string, force = false) {
  return api.post<Shift>(
    `/employee-schedule/shifts/${shiftId}/assignments${force ? '?force=true' : ''}`,
    { employee_id: employeeId },
  )
}

export function unassignEmployee(shiftId: string, employeeId: string) {
  return api.delete<Shift>(`/employee-schedule/shifts/${shiftId}/assignments/${employeeId}`)
}

// ---- Admin: templates ----

export function fetchTemplates() {
  return api.get<{ templates: ShiftTemplate[] }>('/employee-schedule/templates')
}

export function createTemplate(payload: TemplatePayload) {
  return api.post<ShiftTemplate>('/employee-schedule/templates', payload)
}

export function updateTemplate(id: string, payload: TemplatePayload) {
  return api.put<ShiftTemplate>(`/employee-schedule/templates/${id}`, payload)
}

export function deleteTemplate(id: string) {
  return api.delete<{ ok: boolean; id: string }>(`/employee-schedule/templates/${id}`)
}

export function generateFromTemplate(id: string, startDate: string, endDate: string) {
  return api.post<{ created: number; series_id: string; shifts: Shift[] }>(
    `/employee-schedule/templates/${id}/generate`, { start_date: startDate, end_date: endDate },
  )
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
