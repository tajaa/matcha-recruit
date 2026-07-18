import { api } from '../../../api/client'

// ── Project invites ──

export function inviteToProject(projectId: string, email: string) {
  return api.post<{ invited: boolean; email: string }>(`/matcha-work/projects/${projectId}/invite`, { email })
}

export function acceptProjectInvite(projectId: string) {
  return api.post(`/matcha-work/projects/${projectId}/invite/accept`)
}

export function declineProjectInvite(projectId: string) {
  return api.post(`/matcha-work/projects/${projectId}/invite/decline`)
}

export interface PendingInvite {
  project_id: string
  project_title: string
  invited_by: string
  invited_at: string
}

export function listPendingInvites() {
  return api.get<PendingInvite[]>('/matcha-work/project-invites')
}
