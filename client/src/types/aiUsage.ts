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

export type AiUsageSummary = {
  since_hours: number
  totals: AiUsageMetrics
  by_feature: AiUsageFeatureRollup[]
  by_model: AiUsageModelRollup[]
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
  cost_usd: number | null
  latency_ms: number | null
  status: AiUsageStatus
  error: string | null
  created_at: string
}

export type AiUsageCallsResponse = {
  total: number
  items: AiUsageCall[]
}
