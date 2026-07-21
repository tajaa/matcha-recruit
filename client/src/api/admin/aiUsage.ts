import { api } from '../client'
import type {
  AiUsageCallsResponse,
  AiUsageStatus,
  AiUsageSummary,
  AiUsageTimeseries,
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
  status?: AiUsageStatus
  limit?: number
  offset?: number
}) {
  const qs = new URLSearchParams()
  qs.set('since_hours', String(params.sinceHours))
  if (params.feature) qs.set('feature', params.feature)
  if (params.model) qs.set('model', params.model)
  if (params.status) qs.set('status', params.status)
  qs.set('limit', String(params.limit ?? 20))
  qs.set('offset', String(params.offset ?? 0))
  return api.get<AiUsageCallsResponse>(`/admin/ai-usage/calls?${qs.toString()}`)
}
