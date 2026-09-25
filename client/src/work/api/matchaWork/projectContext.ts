import { api } from '../../../api/client'
import type { MWProjectTask } from '../../types'

const root = (projectId: string) => `/matcha-work/projects/${projectId}`

export interface ProjectElement {
  id: string // Opaque server id; deliberately not UUID-validated.
  project_id: string
  name: string
  kind: string | null
  description: string | null
  assigned_to: string | null
  assigned_name?: string | null
  order: number
  repo_paths: string[]
  repo_branch: string | null
  created_at: string
  updated_at: string
}

export interface ElementFile { id: string; filename: string; storage_url: string; folder_id?: string | null }
export interface ElementFolder { id: string; name: string; parent_id: string | null }
export interface ElementNote { id: string; kind: 'note' | 'link'; body: string | null; url: string | null }

export function listProjectElements(projectId: string) {
  return api.get<ProjectElement[]>(`${root(projectId)}/elements`)
}
export function createProjectElement(projectId: string, body: { name: string; kind?: string; description?: string; assigned_to?: string | null; repo_paths?: string[]; repo_branch?: string | null }) {
  return api.post<ProjectElement>(`${root(projectId)}/elements`, body)
}
export function patchProjectElement(projectId: string, elementId: string, patch: Partial<ProjectElement>) {
  return api.patch<ProjectElement>(`${root(projectId)}/elements/${encodeURIComponent(elementId)}`, patch)
}
export function deleteProjectElement(projectId: string, elementId: string) {
  return api.delete(`${root(projectId)}/elements/${encodeURIComponent(elementId)}`)
}
export function getElementSnapshotStats(projectId: string, elementId: string) {
  return api.get<{ files: number; bytes: number; updated_at: string | null }>(`${root(projectId)}/elements/${encodeURIComponent(elementId)}/repo-snapshot/stats`)
}
export function listElementFiles(projectId: string, elementId: string) {
  return api.get<ElementFile[]>(`${root(projectId)}/elements/${encodeURIComponent(elementId)}/files`)
}
export function uploadElementFile(projectId: string, elementId: string, file: File, folderId?: string | null) {
  const form = new FormData()
  form.append('file', file)
  form.append('element_id', elementId)
  if (folderId) form.append('folder_id', folderId)
  return api.upload<ElementFile>(`${root(projectId)}/files`, form)
}
export function listElementFolders(projectId: string, elementId: string) {
  return api.get<ElementFolder[]>(`${root(projectId)}/elements/${encodeURIComponent(elementId)}/folders`)
}
export function createElementFolder(projectId: string, elementId: string, name: string, parentId: string | null) {
  return api.post<ElementFolder>(`${root(projectId)}/elements/${encodeURIComponent(elementId)}/folders`, { name, parent_id: parentId })
}
export function listElementNotes(projectId: string, elementId: string) {
  return api.get<ElementNote[]>(`${root(projectId)}/elements/${encodeURIComponent(elementId)}/notes`)
}
export function addElementNote(projectId: string, elementId: string, body: { kind: 'note' | 'link'; body?: string; url?: string }) {
  return api.post<ElementNote>(`${root(projectId)}/elements/${encodeURIComponent(elementId)}/notes`, body)
}
export function deleteElementNote(projectId: string, elementId: string, noteId: string) {
  return api.delete(`${root(projectId)}/elements/${encodeURIComponent(elementId)}/notes/${noteId}`)
}

export interface GithubConnection { repo: string | null; branch: string | null; connected: boolean; default_repo?: string | null; token_present?: boolean }
export function getGithubConnection(projectId: string) {
  return api.get<GithubConnection>(`${root(projectId)}/github/connection`)
}
export function putGithubConnection(projectId: string, repo: string, branch?: string | null) {
  return api.put<GithubConnection>(`${root(projectId)}/github/connection`, { repo, branch: branch ?? null })
}
export function syncGithubProject(projectId: string) {
  return api.post<{ repo: string; total_stored: number; elements: unknown[] }>(`${root(projectId)}/github/sync`, {})
}
export function scanGithubCommits(projectId: string, force = false) {
  return api.post<{ scanned: number; suggestions: CommitSuggestion[] }>(`${root(projectId)}/github/scan-commits`, { force })
}

export interface CommitSuggestion {
  id: string
  task_id: string
  subtask_id: string
  element_id: string | null
  commit_sha: string
  commit_short_sha: string
  commit_message: string
  confidence: number
  reasoning: string | null
  status: string
}
export function listCommitSuggestions(projectId: string, taskId?: string) {
  return api.get<CommitSuggestion[]>(`${root(projectId)}/commit-suggestions${taskId ? `?task_id=${encodeURIComponent(taskId)}` : ''}`)
}
export function listCommitCompletions(projectId: string, taskId: string) {
  return api.get<CommitSuggestion[]>(`${root(projectId)}/tasks/${taskId}/commit-completions`)
}
export function acceptCommitSuggestion(projectId: string, suggestionId: string) {
  return api.post<{ accepted: boolean }>(`${root(projectId)}/commit-suggestions/${suggestionId}/accept`, {})
}
export function dismissCommitSuggestion(projectId: string, suggestionId: string) {
  return api.post<{ dismissed: boolean }>(`${root(projectId)}/commit-suggestions/${suggestionId}/dismiss`, {})
}

export interface TicketDraft {
  id: string
  project_id: string
  element_id: string | null
  kind: 'feat' | 'fix'
  title: string | null
  description: string | null
  draft_subtasks: string[]
  priority: 'critical' | 'high' | 'medium' | 'low'
  status: 'draft' | 'promoted'
  promoted_task_id: string | null
  updated_at: string
}
export interface TicketDraftMessage { id: string; role: 'user' | 'assistant'; content: string; created_at: string }
export function listTicketDrafts(projectId: string) {
  return api.get<TicketDraft[]>(`${root(projectId)}/ticket-drafts`)
}
export function createTicketDraft(projectId: string, kind: 'feat' | 'fix') {
  return api.post<TicketDraft>(`${root(projectId)}/ticket-drafts`, { kind })
}
export function patchTicketDraft(projectId: string, draftId: string, patch: Partial<TicketDraft>) {
  return api.patch<TicketDraft>(`${root(projectId)}/ticket-drafts/${draftId}`, patch)
}
export function deleteTicketDraft(projectId: string, draftId: string) {
  return api.delete(`${root(projectId)}/ticket-drafts/${draftId}`)
}
export function listTicketDraftMessages(projectId: string, draftId: string) {
  return api.get<TicketDraftMessage[]>(`${root(projectId)}/ticket-drafts/${draftId}/messages`)
}
export function sendTicketDraftMessage(projectId: string, draftId: string, content: string) {
  return api.post<{ user_message: TicketDraftMessage; assistant_message: TicketDraftMessage }>(`${root(projectId)}/ticket-drafts/${draftId}/messages`, { content })
}
export function generateTicketDraft(projectId: string, draftId: string) {
  return api.post<TicketDraft>(`${root(projectId)}/ticket-drafts/${draftId}/generate`, {})
}
export function promoteTicketDraft(projectId: string, draftId: string, overrides: { title: string; category: 'feat' | 'fix'; board_column: 'todo'; priority: TicketDraft['priority'] }) {
  return api.post<MWProjectTask>(`${root(projectId)}/ticket-drafts/${draftId}/promote`, overrides)
}
