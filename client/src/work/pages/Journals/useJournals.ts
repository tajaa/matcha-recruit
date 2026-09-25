import { useCallback, useEffect, useState } from 'react'
import { useEntitlements } from '../../hooks/useEntitlements'
import { showPaywall } from '../../utils/paywall'
import {
  archiveJournal, createJournal, createJournalFolder, deleteJournalFolder,
  listJournalFolders, listJournals, unarchiveJournal, updateJournal,
  updateJournalFolder,
  type FolderPatch, type Journal, type JournalFolder, type JournalKind, type JournalPatch,
} from '../../api/matchaWork/journals'

const premiumKinds = new Set<JournalKind>(['novel', 'screenplay', 'blog'])

export function sharedWithMe(journals: Journal[]): Journal[] {
  return journals.filter((journal) => journal.collaborator_role !== null)
}

// Pick only fields the caller changed. In particular, omitting folder_id and
// sending folder_id: null have different meanings to the server.
export function journalDirtyPatch<K extends keyof JournalPatch>(field: K, value: JournalPatch[K]): JournalPatch {
  return { [field]: value }
}

export function useJournals() {
  const { plan, can } = useEntitlements()
  const [journals, setJournals] = useState<Journal[]>([])
  const [folders, setFolders] = useState<JournalFolder[]>([])
  const [status, setStatus] = useState('active')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      const [nextJournals, nextFolders] = await Promise.all([listJournals(status), listJournalFolders()])
      setJournals(nextJournals)
      setFolders(nextFolders)
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load journals')
    } finally {
      setLoading(false)
    }
  }, [status])

  useEffect(() => {
    const timer = window.setTimeout(() => { void reload() }, 0)
    return () => window.clearTimeout(timer)
  }, [reload])

  const create = async (kind: JournalKind, folderId?: string | null): Promise<Journal | null> => {
    if (premiumKinds.has(kind) && !can('journals_full')) {
      showPaywall('journals_full', 'lite', plan ?? 'free')
      return null
    }
    const body = { title: kind === 'note' ? 'Untitled Note' : `Untitled ${kind}`, kind,
      ...(folderId === undefined ? {} : { folder_id: folderId }) }
    const journal = await createJournal(body)
    await reload()
    return journal
  }

  const patch = async (id: string, changes: JournalPatch) => {
    const updated = await updateJournal(id, changes)
    setJournals((previous) => previous.map((journal) => journal.id === id ? { ...journal, ...updated } : journal))
    return updated
  }

  const archive = async (id: string) => { await archiveJournal(id); await reload() }
  const restore = async (id: string) => { await unarchiveJournal(id); await reload() }
  const createFolder = async (name: string, parentId?: string | null) => {
    const folder = await createJournalFolder({ name, ...(parentId === undefined ? {} : { parent_id: parentId }) })
    setFolders((previous) => [...previous, folder])
    return folder
  }
  const patchFolder = async (id: string, changes: FolderPatch) => {
    const folder = await updateJournalFolder(id, changes)
    setFolders((previous) => previous.map((item) => item.id === id ? folder : item))
  }
  const removeFolder = async (id: string) => { await deleteJournalFolder(id); await reload() }

  return { journals, folders, loading, error, status, setStatus, reload, create, patch, archive, restore,
    createFolder, patchFolder, removeFolder }
}
