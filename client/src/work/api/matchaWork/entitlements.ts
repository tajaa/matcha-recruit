import { api } from '../../../api/client'

export type WorkPlan = 'free' | 'lite' | 'pro' | 'business'

export type WorkEntitlements = {
  plan: WorkPlan
  features: Record<string, boolean>
  quotas: {
    token_limit: number
    window_hours: number
    used?: number
    remaining?: number
    resets_at?: string | null
  }
}

export function getEntitlements() {
  return api.get<WorkEntitlements>('/matcha-work/entitlements')
}
