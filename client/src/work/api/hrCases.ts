import { api } from '../../api/client'
import type { HrCase, HrCaseColumn } from '../types'

// HR cases — the dedicated HR Cases page (business /work only).
// Backend: server/app/matcha/routes/matcha_work/hr_cases.py. Every route is
// HR-only server-side; a non-HR caller gets 404, never a partial list.

const BASE = '/matcha-work/hr-cases'

export const getHrCaseAccess = () => api.get<{ hr_access: boolean }>(`${BASE}/access`)

export const listHrCases = (includeClosed = false) =>
  api.get<{ columns: HrCaseColumn[]; cases: HrCase[] }>(`${BASE}${includeClosed ? '?include_closed=true' : ''}`)

export const getHrCase = (caseId: string) => api.get<HrCase>(`${BASE}/${caseId}`)

export const dismissHrCase = (caseId: string, reason: string) =>
  api.post<HrCase>(`${BASE}/${caseId}/dismiss`, { reason })
