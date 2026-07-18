import { api } from '../../../api/client'

// ── Token Usage ──────────────────────────────────────────────────

export interface UsageSummary {
  period_days: number
  generated_at: string
  totals: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    operation_count: number
    estimated_operations: number
  }
  by_model: Array<{
    model: string
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    operation_count: number
  }>
}

export function fetchUsageSummary(periodDays = 30) {
  return api.get(`/matcha-work/usage/summary?period_days=${periodDays}`) as Promise<UsageSummary>
}

export function fetchUsageSummary24h() {
  return api.get('/matcha-work/usage/summary?period_days=1') as Promise<UsageSummary>
}
