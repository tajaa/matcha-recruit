import { api } from '../../client'
import type {
  PayerPolicyQAResponse,
  PayerPolicy,
  PayerOverviewResponse,
  PayerIntegrityResponse,
} from './types'

// ── Payer Medical Policy Navigator ──

export function askPayerPolicyQuestion(
  question: string,
  locationId?: string,
  payerName?: string,
): Promise<PayerPolicyQAResponse> {
  return api.post<PayerPolicyQAResponse>('/compliance/payer-policies/ask', {
    question,
    location_id: locationId,
    payer_name: payerName,
  })
}

export function fetchPayerPolicies(params: {
  payer_name?: string
  procedure_code?: string
  requires_prior_auth?: boolean
  coverage_status?: string
  limit?: number
  offset?: number
} = {}): Promise<PayerPolicy[]> {
  const searchParams = new URLSearchParams()
  if (params.payer_name) searchParams.set('payer_name', params.payer_name)
  if (params.procedure_code) searchParams.set('procedure_code', params.procedure_code)
  if (params.requires_prior_auth !== undefined) searchParams.set('requires_prior_auth', String(params.requires_prior_auth))
  if (params.coverage_status) searchParams.set('coverage_status', params.coverage_status)
  if (params.limit) searchParams.set('limit', String(params.limit))
  if (params.offset) searchParams.set('offset', String(params.offset))
  const qs = searchParams.toString()
  return api.get<PayerPolicy[]>(`/compliance/payer-policies${qs ? '?' + qs : ''}`)
}

export function researchPayerPolicy(payerName: string, procedure: string): Promise<PayerPolicy> {
  return api.post<PayerPolicy>('/compliance/payer-policies/research', {
    payer_name: payerName,
    procedure,
  })
}

// ── Payer Policy Admin ──

export function fetchPayerOverview() {
  return api.get<PayerOverviewResponse>('/admin/payer-policies/overview')
}

export function fetchPayerIntegrity() {
  return api.get<PayerIntegrityResponse>('/admin/payer-policies/integrity-check')
}

export function runPayerStalenessCheck() {
  return api.post<{ alerts_created: number; alerts_resolved: number; stale_found: number }>(
    '/admin/payer-policies/run-staleness-check', {}
  )
}

export function runCmsIngest(options?: { ncds?: boolean; lcds?: boolean; embed?: boolean }) {
  return api.post('/admin/payer-policies/ingest', {
    ncds: options?.ncds ?? true,
    lcds: options?.lcds ?? true,
    embed: options?.embed ?? true,
  })
}
