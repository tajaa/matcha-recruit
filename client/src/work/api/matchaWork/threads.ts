import { api } from '../../../api/client'
import type {
  MWThread,
  MWThreadDetail,
  MWCreateResponse,
  MWModeKey,
} from '../../types'
import { BASE } from './_base'

// ── Threads ──

export function listThreads(status?: string) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''
  return api.get<MWThread[]>(`/matcha-work/threads${qs}`)
}

export function getThread(id: string) {
  return api.get<MWThreadDetail>(`/matcha-work/threads/${id}`)
}

export function createThread(title?: string, initial_message?: string) {
  return api.post<MWCreateResponse>('/matcha-work/threads', {
    title,
    initial_message,
  })
}

// ── Thread actions ──

export function pinThread(id: string, is_pinned = true) {
  return api.post<MWThread>(`/matcha-work/threads/${id}/pin`, { is_pinned })
}

// Registry-driven mode toggle — key must be a backend THREAD_MODES key.
export function setThreadMode(id: string, mode: MWModeKey, enabled: boolean) {
  return api.post<MWThread>(`/matcha-work/threads/${id}/modes/${mode}`, { enabled })
}

export function archiveThread(id: string) {
  return api.delete(`/matcha-work/threads/${id}`)
}

export function updateTitle(id: string, title: string) {
  return api.patch<MWThread>(`/matcha-work/threads/${id}`, { title })
}

// ── PDF ──

export function getPdf(id: string, version?: number) {
  const qs = version != null ? `?version=${version}` : ''
  return api.get<{ pdf_url: string; version: number }>(
    `/matcha-work/threads/${id}/pdf${qs}`
  )
}

export function getPdfProxyUrl(id: string, version?: number) {
  const qs = version != null ? `?version=${version}` : ''
  return `${BASE}/matcha-work/threads/${id}/pdf/proxy${qs}`
}

// ── Presentation ──

export function generatePresentation(threadId: string) {
  return api.post<{
    thread_id: string
    version: number
    current_state: Record<string, unknown>
    slide_count: number
    generated_at: string
  }>(`/matcha-work/threads/${threadId}/presentation/generate`)
}

export function getPresentationPdf(threadId: string) {
  return api.get<{ pdf_url: string }>(
    `/matcha-work/threads/${threadId}/presentation/pdf`
  )
}

export function uploadPresentationImages(threadId: string, files: File[]) {
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  return api.upload<{ images: string[]; uploaded_count: number }>(
    `/matcha-work/threads/${threadId}/images`,
    form
  )
}

export function removePresentationImage(threadId: string, url: string) {
  return api.delete<{ images: string[] }>(
    `/matcha-work/threads/${threadId}/images?url=${encodeURIComponent(url)}`
  )
}

// ── Thread collaborators ──

export interface ThreadCollaborator {
  user_id: string
  name: string
  email: string
  avatar_url: string | null
  role: 'owner' | 'collaborator'
  created_at: string
}

export function listThreadCollaborators(threadId: string) {
  return api.get<ThreadCollaborator[]>(`/matcha-work/threads/${threadId}/collaborators`)
}

export function addThreadCollaborator(threadId: string, userId: string) {
  return api.post(`/matcha-work/threads/${threadId}/collaborators`, { user_id: userId })
}

export function removeThreadCollaborator(threadId: string, userId: string) {
  return api.delete(`/matcha-work/threads/${threadId}/collaborators/${userId}`)
}

export function searchThreadInvitableUsers(threadId: string, query: string) {
  return api.get<{ user_id: string; name: string; email: string; avatar_url: string | null }[]>(
    `/matcha-work/threads/${threadId}/collaborators/search?q=${encodeURIComponent(query)}`
  )
}
