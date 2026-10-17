import { api } from '../client'
import type {
  AiUsageCallsResponse,
  AiUsageStatus,
  AiUsageSummary,
  AiUsageTimeseries,
  ApiQuotasResponse,
  EspressoUsage,
} from '../../types/aiUsage'

export function getAiUsageSummary(sinceHours: number) {
  return api.get<AiUsageSummary>(`/admin/ai-usage/summary?since_hours=${sinceHours}`)
}

export function getAiUsageTimeseries(sinceHours: number) {
  return api.get<AiUsageTimeseries>(`/admin/ai-usage/timeseries?since_hours=${sinceHours}`)
}

export function getAiUsageCalls(params: {
  sinceHours: number
  feature?: string
  model?: string
  provider?: string
  status?: AiUsageStatus
  limit?: number
  offset?: number
}) {
  const qs = new URLSearchParams()
  qs.set('since_hours', String(params.sinceHours))
  if (params.feature) qs.set('feature', params.feature)
  if (params.model) qs.set('model', params.model)
  if (params.provider) qs.set('provider', params.provider)
  if (params.status) qs.set('status', params.status)
  qs.set('limit', String(params.limit ?? 20))
  qs.set('offset', String(params.offset ?? 0))
  return api.get<AiUsageCallsResponse>(`/admin/ai-usage/calls?${qs.toString()}`)
}

export function getEspressoUsage(sinceHours: number) {
  return api.get<EspressoUsage>(`/admin/ai-usage/espresso?since_hours=${sinceHours}`)
}

// Asks SerpApi's and SearchAPI's account endpoints live (free, a few seconds).
export function getApiQuotas() {
  return api.get<ApiQuotasResponse>('/admin/ai-usage/quotas')
}
