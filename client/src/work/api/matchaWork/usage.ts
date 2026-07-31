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

// ── Usage meter (live position against the walls a turn can hit) ──

export interface UsageMeter {
  user_quota: {
    plan: string
    used: number
    limit: number
    remaining: number
    window_hours: number
    resets_at: string
  } | null
  company_budget: {
    free_tokens_remaining: number
    subscription_tokens_remaining: number
    total_tokens_remaining: number
    free_token_limit: number
    subscription_token_limit: number
    has_active_subscription: boolean
  } | null
  huume_turns: {
    used: number
    limit: number
    remaining: number
    resets_in_seconds: number
  } | null
}

export function fetchUsageMeter() {
  return api.get('/matcha-work/usage/meter') as Promise<UsageMeter>
}

// Fired after a turn completes (or errors) so the shell's TokenIndicator can
// refresh without polling — mirrors threads.ts's THREADS_CHANGED_EVENT.
export const USAGE_CHANGED_EVENT = 'mw-usage-changed'

export function notifyUsageChanged() {
  window.dispatchEvent(new CustomEvent(USAGE_CHANGED_EVENT))
}
