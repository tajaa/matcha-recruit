import { api } from '../../client'
import type {
  KeyCoverageResponse,
  IntegrityCheckResponse,
} from './types'

// ── Key Coverage & Integrity (Admin) ──

export function fetchKeyCoverage(params?: {
  jurisdiction_id?: string
  category?: string
  state?: string
  gaps_only?: boolean
}) {
  const parts: string[] = []
  if (params?.jurisdiction_id) parts.push(`jurisdiction_id=${params.jurisdiction_id}`)
  if (params?.category) parts.push(`category=${encodeURIComponent(params.category)}`)
  if (params?.state) parts.push(`state=${encodeURIComponent(params.state)}`)
  if (params?.gaps_only) parts.push('gaps_only=true')
  const qs = parts.length ? `?${parts.join('&')}` : ''
  return api.get<KeyCoverageResponse>(`/admin/jurisdictions/key-coverage${qs}`)
}

export function fetchIntegrityCheck(params?: {
  jurisdiction_id?: string
  state?: string
}) {
  const parts: string[] = []
  if (params?.jurisdiction_id) parts.push(`jurisdiction_id=${params.jurisdiction_id}`)
  if (params?.state) parts.push(`state=${encodeURIComponent(params.state)}`)
  const qs = parts.length ? `?${parts.join('&')}` : ''
  return api.get<IntegrityCheckResponse>(`/admin/jurisdictions/integrity-check${qs}`)
}

export function runStalenessCheck(params?: {
  jurisdiction_id?: string
  state?: string
}) {
  return api.post<{
    alerts_created: number
    alerts_resolved: number
    stale_found: number
    missing_found: number
  }>('/admin/jurisdictions/run-staleness-check', params || {})
}
