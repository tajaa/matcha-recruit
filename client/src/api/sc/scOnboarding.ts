import { api } from '../client'
import type {
  ScEmployeeImport,
  ScLocationImport,
  ScOnboardingStatus,
  ScOnboardingSubmission,
} from '../../types/scOnboarding'

/** Parsing and row validation live on the server (services/employees/roster_csv.py)
 *  so the wizard can never accept a file `/complete` would refuse. Nothing is
 *  written — the rows come back and sit in the wizard until the final review. */
function parseCsv<T>(kind: 'locations' | 'employees', file: File) {
  const body = new FormData()
  body.append('file', file)
  return api.upload<{ rows: T[] }>(`/sc-onboarding/csv/${kind}`, body).then((r) => r.rows)
}

export const scOnboardingApi = {
  status: () => api.get<ScOnboardingStatus>('/sc-onboarding/status'),
  parseLocationsCsv: (file: File) => parseCsv<ScLocationImport>('locations', file),
  parseEmployeesCsv: (file: File) => parseCsv<ScEmployeeImport>('employees', file),
  complete: (submission: ScOnboardingSubmission) =>
    api.post<{ already_completed: boolean; completed_at: string }>(
      '/sc-onboarding/complete',
      submission,
    ),
}
