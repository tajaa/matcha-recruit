import { api } from '../../../api/client'
import type { RecruitingClient } from '../../types'

// ── Recruiting clients ──

export function listRecruitingClients(includeArchived = false) {
  const qs = includeArchived ? '?include_archived=true' : ''
  return api.get<RecruitingClient[]>(`/matcha-work/recruiting-clients${qs}`)
}

export function createRecruitingClient(data: {
  name: string
  website?: string | null
  logo_url?: string | null
  notes?: string | null
}) {
  return api.post<RecruitingClient>('/matcha-work/recruiting-clients', data)
}

export function updateRecruitingClient(id: string, updates: Partial<Omit<RecruitingClient, 'id' | 'created_at' | 'updated_at' | 'archived_at' | 'project_count'>>) {
  return api.patch<RecruitingClient>(`/matcha-work/recruiting-clients/${id}`, updates)
}

export function archiveRecruitingClient(id: string) {
  return api.post<{ status: string }>(`/matcha-work/recruiting-clients/${id}/archive`, {})
}

export function unarchiveRecruitingClient(id: string) {
  return api.post<{ status: string }>(`/matcha-work/recruiting-clients/${id}/unarchive`, {})
}
