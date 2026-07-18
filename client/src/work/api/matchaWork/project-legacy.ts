import { api } from '../../../api/client'

// ── Project (legacy thread-scoped) ──

export function initProject(threadId: string, title: string) {
  return api.post<{ current_state: Record<string, unknown>; version: number }>(
    `/matcha-work/threads/${threadId}/project/init`,
    { title }
  )
}

export function addProjectSection(threadId: string, section: { title?: string; content: string; source_message_id?: string }) {
  return api.post<{ section: { id: string }; current_state: Record<string, unknown>; version: number }>(
    `/matcha-work/threads/${threadId}/project/sections`,
    section
  )
}

export function updateProjectSection(threadId: string, sectionId: string, updates: { title?: string; content?: string }) {
  return api.put<{ current_state: Record<string, unknown>; version: number }>(
    `/matcha-work/threads/${threadId}/project/sections/${sectionId}`,
    updates
  )
}

export function deleteProjectSection(threadId: string, sectionId: string) {
  return api.delete<{ current_state: Record<string, unknown>; version: number }>(
    `/matcha-work/threads/${threadId}/project/sections/${sectionId}`
  )
}

export function reorderProjectSections(threadId: string, sectionIds: string[]) {
  return api.put<{ current_state: Record<string, unknown>; version: number }>(
    `/matcha-work/threads/${threadId}/project/sections/reorder`,
    { section_ids: sectionIds }
  )
}

export function exportProject(threadId: string, format: 'pdf' | 'md' | 'docx') {
  return api.get<{ pdf_url?: string; docx_url?: string }>(
    `/matcha-work/threads/${threadId}/project/export/${format}`
  )
}

export function uploadProjectImage(threadId: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return api.upload<{ url: string; filename: string }>(
    `/matcha-work/threads/${threadId}/project/images`,
    form
  )
}
