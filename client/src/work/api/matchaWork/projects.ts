import { api } from '../../../api/client'
import type { MWProject, MWThread, ProjectCollaborator } from '../../types'

// ── Projects (top-level) ──

export function listProjects(status?: string) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''
  return api.get<MWProject[]>(`/matcha-work/projects${qs}`)
}

export function createProjectNew(
  title: string,
  projectType: string = 'general',
  hiringClientId?: string | null,
  template?: string | null,
) {
  return api.post<MWProject>('/matcha-work/projects', {
    title,
    project_type: projectType,
    hiring_client_id: hiringClientId ?? null,
    template: template ?? null,
  })
}

export function getProjectDetail(id: string) {
  return api.get<MWProject>(`/matcha-work/projects/${id}`)
}

export function updateProjectMeta(id: string, updates: Record<string, unknown>) {
  return api.patch<MWProject>(`/matcha-work/projects/${id}`, updates)
}

export function archiveProjectById(id: string) {
  return api.delete(`/matcha-work/projects/${id}`)
}

export function addProjectSectionNew(projectId: string, section: { title?: string; content: string; source_message_id?: string }) {
  return api.post<{ section: { id: string } }>(`/matcha-work/projects/${projectId}/sections`, section)
}

export function updateProjectSectionNew(projectId: string, sectionId: string, updates: { title?: string; content?: string }) {
  return api.put(`/matcha-work/projects/${projectId}/sections/${sectionId}`, updates)
}

export function deleteProjectSectionNew(projectId: string, sectionId: string) {
  return api.delete(`/matcha-work/projects/${projectId}/sections/${sectionId}`)
}

export function reorderProjectSectionsNew(projectId: string, sectionIds: string[]) {
  return api.put(`/matcha-work/projects/${projectId}/sections/reorder`, { section_ids: sectionIds })
}

export function editDiagramAI(projectId: string, sectionId: string, instruction: string, region?: { x: number; y: number; width: number; height: number }) {
  return api.post<MWProject>(`/matcha-work/projects/${projectId}/sections/${sectionId}/edit-diagram`, { instruction, ...(region ? { region } : {}) })
}

export function editDiagramText(projectId: string, sectionId: string, edits: { old_text: string; new_text: string }[]) {
  return api.post<MWProject>(`/matcha-work/projects/${projectId}/sections/${sectionId}/edit-diagram-text`, { edits })
}

export function saveDiagramSVG(projectId: string, sectionId: string, svg: string) {
  return api.post<MWProject>(`/matcha-work/projects/${projectId}/sections/${sectionId}/save-diagram`, { svg })
}

export function createProjectChat(projectId: string, title?: string) {
  return api.post<MWThread>(`/matcha-work/projects/${projectId}/chats`, { title })
}

/**
 * Get-or-create the collab project's discussion CHANNEL — the real per-project
 * chat (desktop Werk has used this since day one; the web project view used to
 * show the AI `mw_threads` list instead, so the actual conversation was only
 * reachable by hunting through the Channels sidebar).
 *
 * Idempotent server-side: returns the existing
 * `project_data.discussion_channel_id` when set, otherwise creates the private
 * channel and syncs collaborators as members. 400s for non-collab projects.
 */
export function ensureDiscussionChannel(projectId: string) {
  return api.post<{ channel_id: string }>(`/matcha-work/projects/${projectId}/discussion-channel`, {})
}

// ── Collaborators ──

export function listCollaborators(projectId: string) {
  return api.get<ProjectCollaborator[]>(`/matcha-work/projects/${projectId}/collaborators`)
}

export function addCollaborator(projectId: string, userId: string) {
  return api.post<ProjectCollaborator[]>(`/matcha-work/projects/${projectId}/collaborators`, { user_id: userId })
}

export function removeCollaborator(projectId: string, userId: string) {
  return api.delete<ProjectCollaborator[]>(`/matcha-work/projects/${projectId}/collaborators/${userId}`)
}

export function searchAdminUsers(query: string) {
  return api.get<{ user_id: string; name: string; email: string; avatar_url: string | null }[]>(
    `/matcha-work/admin-users/search?q=${encodeURIComponent(query)}`
  )
}

export function exportProjectNew(projectId: string, format: 'pdf' | 'md' | 'docx') {
  return api.get<{ pdf_url?: string; docx_url?: string }>(`/matcha-work/projects/${projectId}/export/${format}`)
}

// ── Project file attachments ──

export interface ProjectFile {
  id: string
  project_id: string
  filename: string
  storage_url: string
  content_type: string | null
  file_size: number
  created_at: string
}

export function listProjectFiles(projectId: string) {
  return api.get<ProjectFile[]>(`/matcha-work/projects/${projectId}/files`)
}

export function uploadProjectFile(projectId: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return api.upload<ProjectFile>(
    `/matcha-work/projects/${projectId}/files`,
    form,
  )
}

export function deleteProjectFile(projectId: string, fileId: string) {
  return api.delete(`/matcha-work/projects/${projectId}/files/${fileId}`)
}
