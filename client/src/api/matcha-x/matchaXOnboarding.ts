/**
 * Typed wrappers for the Matcha-X self-serve onboarding wizard backend
 * (/api/matcha-x-onboarding/*). The live "build" finale is consumed as an SSE
 * stream via fetch + ReadableStream (see components/matcha-x/onboarding/useMatchaXBuildStream) — only the
 * status/complete/upload helpers go through the `api` client here.
 */

import { api } from '../client'

export type MatchaXStep = 'locations' | 'policies' | 'people' | 'build' | 'done'

export type MatchaXOnboardingStatus = {
  step: MatchaXStep
  locations_count: number
  employees_count: number
  handbook_present: boolean
  built: boolean
}

// Absolute URL for the SSE build stream — POSTed with a JSON body and read via
// fetch + ReadableStream (not EventSource) so the Authorization header attaches.
// Mirrors getEnrichStreamUrl in api/adminOnboarding.ts.
export function getMatchaXBuildStreamUrl(): string {
  const base = import.meta.env.VITE_API_URL || '/api'
  return `${base}/matcha-x-onboarding/build/stream`
}

export const matchaXOnboarding = {
  status: () =>
    api.get<MatchaXOnboardingStatus>('/matcha-x-onboarding/status'),

  complete: () =>
    api.post<{ completed: boolean }>('/matcha-x-onboarding/complete'),

  // Uploads a handbook PDF under a per-company key prefix; returns the storage
  // URL the build stream consumes for the live coverage overlay. The build
  // verifies the URL belongs to the caller before downloading (IDOR guard), so
  // this must NOT use the generic /handbooks/upload (no per-company namespace).
  uploadHandbook: (fd: FormData) =>
    api.upload<{ url: string; filename: string }>('/matcha-x-onboarding/handbook-upload', fd),
}
