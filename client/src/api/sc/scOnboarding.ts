import { api } from '../client'
import type { ScOnboardingStatus, ScOnboardingSubmission } from '../../types/scOnboarding'

export const scOnboardingApi = {
  status: () => api.get<ScOnboardingStatus>('/sc-onboarding/status'),
  complete: (submission: ScOnboardingSubmission) =>
    api.post<{ already_completed: boolean; completed_at: string }>(
      '/sc-onboarding/complete',
      submission,
    ),
}
