import { api } from '../../client'
import type {
  ComplianceRequirement,
  PinnedRequirement,
  RequirementComponent,
  RequirementComponentChecklist,
} from '../../../types/compliance'

// ── Requirements ──

export function fetchRequirements(locationId: string, category?: string) {
  const params = category ? `?category=${encodeURIComponent(category)}` : ''
  return api.get<ComplianceRequirement[]>(
    `/compliance/locations/${locationId}/requirements${params}`
  )
}

export function pinRequirement(requirementId: string, isPinned: boolean) {
  return api.post(`/compliance/requirements/${requirementId}/pin`, {
    is_pinned: isPinned,
  })
}

export function fetchPinnedRequirements() {
  return api.get<PinnedRequirement[]>('/compliance/pinned-requirements')
}

// ── Component checklist (reqcomp01) ──

export function fetchRequirementComponents(
  locationId: string,
  catalogId: string,
  companyId?: string
) {
  const qs = companyId ? `?company_id=${encodeURIComponent(companyId)}` : ''
  return api.get<RequirementComponentChecklist>(
    `/compliance/locations/${locationId}/requirements/${catalogId}/components${qs}`
  )
}

export function attestRequirementComponent(
  locationId: string,
  catalogId: string,
  componentKey: string,
  body: { status: RequirementComponent['status']; note?: string | null },
  companyId?: string
) {
  const qs = companyId ? `?company_id=${encodeURIComponent(companyId)}` : ''
  return api.post<RequirementComponent>(
    `/compliance/locations/${locationId}/requirements/${catalogId}/components/${componentKey}/attest${qs}`,
    body
  )
}
