import { api } from '../client'

export type OpsCompany = {
  company_id: string
  company_name: string
  status: string
  signup_source: string | null
  is_personal: boolean
  matcha_ops_enabled: boolean
  enabled_ops_features: string[]
  channel_count: number
  operations_channel_count: number
  open_events: number
  low_stock_items: number
  open_orders: number
  upcoming_shifts: number
  pending_schedule_requests: number
  needs_attention: boolean
}

export type OpsOverview = {
  companies_enabled: number
  companies_with_attention: number
  operations_channels: number
  open_events: number
  low_stock_items: number
  open_orders: number
  upcoming_shifts: number
  pending_schedule_requests: number
}

export type OpsCompanyDetail = OpsCompany & {
  stored_features: Record<string, boolean>
  effective_features: Record<string, boolean>
  dependency_violations: Record<string, string[]>
  feature_provenance: Record<string, unknown>
  created_at: string | null
}

export function getOpsOverview() {
  return api.get<OpsOverview>('/admin/matcha-ops/overview')
}

export function listOpsCompanies(params: URLSearchParams = new URLSearchParams()) {
  const query = params.toString()
  return api.get<{ companies: OpsCompany[]; total: number }>(
    `/admin/matcha-ops/companies${query ? `?${query}` : ''}`,
  )
}

export function getOpsCompany(companyId: string) {
  return api.get<OpsCompanyDetail>(`/admin/matcha-ops/companies/${companyId}`)
}

export function updateOpsCompanyFeatures(companyId: string, features: Record<string, boolean>) {
  return api.patch<OpsCompanyDetail>(`/admin/matcha-ops/companies/${companyId}/features`, { features })
}
