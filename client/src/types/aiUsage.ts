// ── AI usage ledger (/admin/ai-usage) ──

export type AiUsageStatus = 'ok' | 'error' | 'timeout'

export type AiUsageMetrics = {
  calls: number
  cost_usd: number | null
  input_tokens: number
  output_tokens: number
  thinking_tokens: number
  cached_tokens: number
  errors: number
  error_rate: number
  unknown_cost_calls: number
  avg_latency_ms: number | null
  p95_latency_ms: number | null
}

export type AiUsageFeatureRollup = AiUsageMetrics & { feature: string }
export type AiUsageModelRollup = AiUsageMetrics & { provider: string; model: string }
export type AiUsageProviderRollup = AiUsageMetrics & { provider: string }

export type AiUsageSummary = {
  since_hours: number
  totals: AiUsageMetrics
  by_feature: AiUsageFeatureRollup[]
  by_model: AiUsageModelRollup[]
  by_provider: AiUsageProviderRollup[]
}

export type AiUsagePoint = {
  at: string
  calls: number
  cost_usd: number | null
  errors: number
}

export type AiUsageTimeseries = {
  bucket: 'hour' | 'day'
  points: AiUsagePoint[]
}

export type AiUsageCall = {
  id: number
  provider: string
  model: string
  feature: string
  method: string
  input_tokens: number | null
  output_tokens: number | null
  thinking_tokens: number | null
  cached_tokens: number | null
  cache_write_tokens: number | null
  cost_usd: number | null
  latency_ms: number | null
  status: AiUsageStatus
  error: string | null
  provider_response_id?: string | null
  provider_status?: string | null
  service_tier?: string | null
  created_at: string
}

export type AiUsageCallsResponse = {
  total: number
  items: AiUsageCall[]
}

// ── Espresso runs + tools (/admin/ai-usage/espresso) ──

export type EspressoRunRollup = {
  kind: string
  runs: number
  done: number
  failed: number
  live: number
  people: number
  model_calls: number
  search_calls: number
  avg_seconds: number | null
}

export type EspressoToolRollup = {
  tool: string
  kind: string
  calls: number
  ok: number
  errors: number
  skipped: number
  held: number
  unknown: number
  runs: number
  run_kinds: string[]
  last_used_at: string | null
}

export type EspressoUsage = {
  since_hours: number
  spend: AiUsageModelRollup[]
  totals: {
    cost_usd: number | null
    runs: number
    failed: number
    people: number
    model_calls: number
    search_calls: number
    tool_calls: number
  }
  runs: EspressoRunRollup[]
  tools: EspressoToolRollup[]
}

// ── Search API quotas (/admin/ai-usage/quotas) ──

export type ApiQuota = {
  provider: string
  label: string
  configured: boolean
  source: 'headers' | 'account_api' | null
  plan: string | null
  monthly_price: number | null
  limit: number | null
  remaining: number | null
  used: number | null
  extra_credits: number | null
  resets_at: string | null
  observed_at: string | null
  error: string | null
  note: string | null
}

export type ApiQuotasResponse = {
  providers: ApiQuota[]
}
