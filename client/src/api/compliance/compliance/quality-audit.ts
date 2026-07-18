import { api } from '../../client'
import type {
  QualityAuditResponse,
  CoverageMatrixResponse,
} from './types'

// ── Quality Audit API ──

export function fetchQualityAudit(params: {
  state?: string
  category?: string
  min_completeness?: number
  max_completeness?: number
  stale_only?: boolean
  tier?: string
  source?: string
  citation?: 'verified' | 'unverified'
  needs_review?: boolean
  limit?: number
  offset?: number
}): Promise<QualityAuditResponse> {
  const searchParams = new URLSearchParams()
  if (params.state) searchParams.set('state', params.state)
  if (params.category) searchParams.set('category', params.category)
  if (params.min_completeness != null) searchParams.set('min_completeness', String(params.min_completeness))
  if (params.max_completeness != null) searchParams.set('max_completeness', String(params.max_completeness))
  if (params.stale_only) searchParams.set('stale_only', 'true')
  if (params.tier) searchParams.set('tier', params.tier)
  if (params.source) searchParams.set('source', params.source)
  if (params.citation) searchParams.set('citation', params.citation)
  if (params.needs_review) searchParams.set('needs_review', 'true')
  if (params.limit != null) searchParams.set('limit', String(params.limit))
  if (params.offset != null) searchParams.set('offset', String(params.offset))

  const qs = searchParams.toString()
  return api.get<QualityAuditResponse>(`/admin/jurisdictions/quality-audit${qs ? '?' + qs : ''}`)
}

export function fetchCoverageMatrix(params: {
  state?: string
  domain?: string
} = {}): Promise<CoverageMatrixResponse> {
  const searchParams = new URLSearchParams()
  if (params.state) searchParams.set('state', params.state)
  if (params.domain) searchParams.set('domain', params.domain)

  const qs = searchParams.toString()
  return api.get<CoverageMatrixResponse>(`/admin/jurisdictions/coverage-matrix${qs ? '?' + qs : ''}`)
}
