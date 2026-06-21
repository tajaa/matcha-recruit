import { api } from './client'
import type {
  SafetyProgram, MvrReview, ResidentCareSummary, ProgramType, ProgramStatus, ReviewType, MvrStatus,
} from '../types/residentCare'

export function fetchResidentCareSummary() {
  return api.get<ResidentCareSummary>('/resident-care/summary')
}

// --- safety programs ---
export function fetchSafetyPrograms() {
  return api.get<SafetyProgram[]>('/resident-care/programs')
}
export function createSafetyProgram(payload: {
  program_type: ProgramType; name: string; status?: ProgramStatus
  last_reviewed_date?: string | null; owner?: string | null; notes?: string | null
}) {
  return api.post<SafetyProgram>('/resident-care/programs', payload)
}
export function updateSafetyProgram(id: string, payload: Record<string, unknown>) {
  return api.put<SafetyProgram>(`/resident-care/programs/${id}`, payload)
}
export function deleteSafetyProgram(id: string) {
  return api.delete<{ status: string }>(`/resident-care/programs/${id}`)
}
export interface ProgramSuggestion { program_type: ProgramType; name: string }
export function suggestSafetyPrograms() {
  return api.post<{ suggestions: ProgramSuggestion[]; available: boolean }>('/resident-care/programs/suggest', {})
}

// --- MVR reviews ---
export function fetchMvrReviews() {
  return api.get<MvrReview[]>('/resident-care/mvr')
}
export function createMvrReview(payload: {
  driver_name: string; review_type?: ReviewType; review_date?: string | null
  status?: MvrStatus; next_due_date?: string | null; notes?: string | null
}) {
  return api.post<MvrReview>('/resident-care/mvr', payload)
}
export function updateMvrReview(id: string, payload: Record<string, unknown>) {
  return api.put<MvrReview>(`/resident-care/mvr/${id}`, payload)
}
export function deleteMvrReview(id: string) {
  return api.delete<{ status: string }>(`/resident-care/mvr/${id}`)
}

// --- insurer-facing asset PDF ---
export function downloadResidentCareAsset() {
  return api.download('/resident-care/asset.pdf', 'resident-care-asset.pdf')
}
