import { api } from '../../client'
import type {
  ComplianceRequirement,
  PinnedRequirement,
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
