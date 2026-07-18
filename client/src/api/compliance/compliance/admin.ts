import { api } from '../../client'
import type {
  BusinessLocation,
  LocationCreate,
  ComplianceRequirement,
} from '../../../types/compliance'

// ── Admin Compliance Management ──

export function fetchCompanyCompliance(companyId: string) {
  return api.get<{
    company: { id: string; name: string; industry: string | null }
    locations: (BusinessLocation & { category_counts: Record<string, number> })[]
  }>(`/admin/companies/${companyId}/compliance`)
}

export function fetchAdminLocationRequirements(companyId: string, locationId: string, category?: string) {
  const qs = category ? `?category=${encodeURIComponent(category)}` : ''
  return api.get<{ requirements: (ComplianceRequirement & { governance_source: string })[] }>(
    `/admin/companies/${companyId}/locations/${locationId}/requirements${qs}`,
  )
}

export function adminCreateLocation(companyId: string, data: LocationCreate) {
  return api.post<{ location: BusinessLocation; has_coverage: boolean }>(
    `/admin/companies/${companyId}/locations`, data,
  )
}

export function adminAddRequirement(companyId: string, locationId: string, jurisdictionRequirementId: string) {
  return api.post(`/admin/companies/${companyId}/locations/${locationId}/requirements`, {
    jurisdiction_requirement_id: jurisdictionRequirementId,
  })
}

export function adminRemoveRequirement(companyId: string, locationId: string, requirementId: string) {
  return api.delete(`/admin/companies/${companyId}/locations/${locationId}/requirements/${requirementId}`)
}

export function fetchRepositoryRequirements(companyId: string, locationId: string) {
  return api.get<{ requirements: {
    id: string; category: string; regulation_key: string; jurisdiction_level: string
    jurisdiction_name: string; title: string; description: string | null
    current_value: string | null; source_url: string | null; effective_date: string | null
  }[] }>(`/admin/companies/${companyId}/locations/${locationId}/repository`)
}
