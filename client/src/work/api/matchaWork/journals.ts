import { api } from '../../../api/client'

export type JournalKind = 'note' | 'blog' | 'todo' | 'novel' | 'screenplay' | 'journal'

export interface Journal {
  id: string
  title: string
  description: string | null
  color: string | null
  icon: string | null
  status: string
  kind: JournalKind
  folder_id: string | null
  created_by: string
  owner_name: string | null
  created_at: string
  updated_at: string
  entry_count: number
  collaborator_count: number
  collaborator_role: string | null
  preview: string | null
}

export interface JournalEntry {
  id: string
  journal_id: string
  author_id: string
  title: string | null
  content: string
  entry_date: string | null
  created_at: string
  updated_at: string
}

export interface JournalFolder {
  id: string
  name: string
  parent_id: string | null
  created_by: string
  created_at: string
  color: string | null
}

export interface JournalCollaborator {
  user_id: string
  name: string
  email: string
  avatar_url: string | null
  role: string
  created_at: string
}

export type JournalPatch = Partial<Pick<Journal, 'title' | 'description' | 'color' | 'icon' | 'kind' | 'folder_id'>>
export type FolderPatch = Partial<Pick<JournalFolder, 'name' | 'parent_id' | 'color'>>
export type EntryPatch = Partial<Pick<JournalEntry, 'title' | 'content' | 'entry_date'>>

const journalPath = (id: string) => `/matcha-work/journals/${encodeURIComponent(id)}`
const folderPath = (id: string) => `/matcha-work/journal-folders/${encodeURIComponent(id)}`
const entryPath = (journalId: string, entryId: string) => `${journalPath(journalId)}/entries/${encodeURIComponent(entryId)}`

export const listJournals = (status = 'active') =>
  api.get<Journal[]>(`/matcha-work/journals?status=${encodeURIComponent(status)}`)
export const createJournal = (body: { title: string; kind?: JournalKind; description?: string; color?: string; icon?: string; folder_id?: string | null }) =>
  api.post<Journal>('/matcha-work/journals', body)
export const getJournal = (id: string) => api.get<Journal>(journalPath(id))
export const updateJournal = (id: string, patch: JournalPatch) => api.patch<Journal>(journalPath(id), patch)
export const archiveJournal = (id: string) => api.delete<null>(journalPath(id))
export const unarchiveJournal = (id: string) => api.post<{ ok: boolean }>(`${journalPath(id)}/unarchive`)
export const deleteJournalPermanently = (id: string) => api.delete<null>(`${journalPath(id)}/permanent`)

export const listJournalFolders = () => api.get<JournalFolder[]>('/matcha-work/journal-folders')
export const createJournalFolder = (body: { name: string; parent_id?: string | null; color?: string }) =>
  api.post<JournalFolder>('/matcha-work/journal-folders', body)
export const updateJournalFolder = (id: string, patch: FolderPatch) => api.patch<JournalFolder>(folderPath(id), patch)
export const deleteJournalFolder = (id: string) => api.delete<null>(folderPath(id))

export const listJournalEntries = (id: string, limit = 50, before?: string) =>
  api.get<JournalEntry[]>(`${journalPath(id)}/entries?limit=${limit}${before ? `&before=${encodeURIComponent(before)}` : ''}`)
export const createJournalEntry = (id: string, body: { title?: string | null; content?: string; entry_date?: string | null }) =>
  api.post<JournalEntry>(`${journalPath(id)}/entries`, body)
export const updateJournalEntry = (journalId: string, entryId: string, patch: EntryPatch) =>
  api.patch<JournalEntry>(entryPath(journalId, entryId), patch)
export const deleteJournalEntry = (journalId: string, entryId: string) => api.delete<null>(entryPath(journalId, entryId))
export const uploadJournalImage = (id: string, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.upload<{ url: string }>(`${journalPath(id)}/images`, form)
}

export const listJournalCollaborators = (id: string) => api.get<JournalCollaborator[]>(`${journalPath(id)}/collaborators`)
export const addJournalCollaborators = (id: string, userIds: string[]) =>
  api.post<{ added: number }>(`${journalPath(id)}/collaborators`, { user_ids: userIds })
export const removeJournalCollaborator = (id: string, userId: string) =>
  api.delete<null>(`${journalPath(id)}/collaborators/${encodeURIComponent(userId)}`)
