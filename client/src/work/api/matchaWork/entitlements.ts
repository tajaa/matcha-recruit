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
    /** Agent-card runs this UTC month (server: agent_card/quota.py). */
    agent_runs?: { limit: number; used: number; remaining: number; resets_at: string }
    /** Espresso assistant requests this UTC day (server: agent_runtime/quota.py). */
    assistant_runs?: { limit: number; used: number; remaining: number; resets_at: string }
  }
}

export function getEntitlements() {
  return api.get<WorkEntitlements>('/matcha-work/entitlements')
}
