/**
 * Session lifecycle endpoints — specialties lookup, session list/read/create,
 * step patching, and company creation.
 */

import { api } from '../../client'
import type {
  BasicsPayload,
  CreateCompanyResponse,
  LocationInput,
  OnboardingSessionDetail,
  OnboardingSessionSummary,
  OnboardingStatus,
  OnboardingStep,
  SizePayload,
} from './types'

const BASE = '/admin/onboarding'

export const sessionsApi = {
  specialties: () =>
    api.get<Record<string, string[]>>(`${BASE}/specialties`),

  listSessions: (status?: OnboardingStatus) =>
    api.get<OnboardingSessionSummary[]>(
      status ? `${BASE}/sessions?status_filter=${status}` : `${BASE}/sessions`,
    ),

  getSession: (id: string) =>
    api.get<OnboardingSessionDetail>(`${BASE}/sessions/${id}`),

  createSession: (idempotency_key: string) =>
    api.post<OnboardingSessionDetail>(`${BASE}/sessions`, { idempotency_key }),

  patchSession: (
    id: string,
    body: {
      step?: OnboardingStep
      basics?: BasicsPayload
      size?: SizePayload
      locations?: { locations: LocationInput[] }
    },
  ) =>
    api.patch<OnboardingSessionDetail>(`${BASE}/sessions/${id}`, body),

  createCompany: (id: string) =>
    api.post<CreateCompanyResponse>(`${BASE}/sessions/${id}/create-company`),
}
