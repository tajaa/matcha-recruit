import { useCallback, useSyncExternalStore } from 'react'
import { listChannels } from '../api/channels'
import { listThreads, listProjects } from '../api/matchaWork'
import { listJournals } from '../api/matchaWork/journals'

export type SearchKind = 'thread' | 'channel' | 'project' | 'journal' | 'file'
export type SearchItem = {
  kind: SearchKind
  id: string
  title: string
  updatedAt?: string
  projectId?: string
  url?: string
}

type Index = { items: SearchItem[]; ready: boolean }
const EMPTY: Index = { items: [], ready: false }
const indexes = new Map<string, { sources: Map<string, SearchItem[]>; snapshot: Index; listeners: Set<() => void> }>()
const pending = new Map<string, Promise<void>>()

function getState(userId: string) {
  let state = indexes.get(userId)
  if (!state) {
    state = { sources: new Map(), snapshot: EMPTY, listeners: new Set() }
    indexes.set(userId, state)
  }
  return state
}

export function publishSearchSource(userId: string | null | undefined, source: string, items: SearchItem[], ready = false) {
  if (!userId) return
  const state = getState(userId)
  state.sources.set(source, items)
  state.snapshot = { items: [...state.sources.values()].flat(), ready: state.snapshot.ready || ready }
  state.listeners.forEach((listener) => listener())
}

export function clearSearchSource(userId: string | null | undefined, source: string) {
  if (!userId) return
  const state = getState(userId)
  state.sources.delete(source)
  state.snapshot = { items: [...state.sources.values()].flat(), ready: state.snapshot.ready }
  state.listeners.forEach((listener) => listener())
}

export function getSearchIndex(userId: string | null | undefined): Index {
  return userId ? getState(userId).snapshot : EMPTY
}

export function useSearchIndex(userId: string | null | undefined): Index {
  const subscribe = useCallback((listener: () => void) => {
    if (!userId) return () => {}
    const state = getState(userId)
    state.listeners.add(listener)
    return () => { state.listeners.delete(listener) }
  }, [userId])
  const snapshot = useCallback(() => getSearchIndex(userId), [userId])
  return useSyncExternalStore(subscribe, snapshot, () => EMPTY)
}

export function rankSearch(items: SearchItem[], query: string): SearchItem[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return []
  const time = (value?: string) => value ? Date.parse(value) || 0 : 0
  return items.filter((item) => item.title.toLowerCase().includes(needle)).sort((a, b) => {
    const position = a.title.toLowerCase().indexOf(needle) - b.title.toLowerCase().indexOf(needle)
    return position || time(b.updatedAt) - time(a.updatedAt) || a.title.localeCompare(b.title)
  })
}

// On desktop the sidebar publishes its already-loaded lists. Mobile has no
// mounted sidebar until the drawer opens, so this fills the same cache once.
export function ensureSearchCatalog(userId: string): Promise<void> {
  if (getSearchIndex(userId).ready) return Promise.resolve()
  const active = pending.get(userId)
  if (active) return active
  const request = Promise.allSettled([listThreads('active'), listProjects(), listChannels(), listJournals()])
    .then(([threads, projects, channels, journals]) => {
      publishSearchSource(userId, 'threads', threads.status === 'fulfilled' ? threads.value.map((item) => ({ kind: 'thread', id: item.id, title: item.title, updatedAt: item.updated_at })) : [])
      publishSearchSource(userId, 'projects', projects.status === 'fulfilled' ? projects.value.map((item) => ({ kind: 'project', id: item.id, title: item.title, updatedAt: item.updated_at })) : [])
      publishSearchSource(userId, 'channels', channels.status === 'fulfilled' ? channels.value.map((item) => ({ kind: 'channel', id: item.id, title: item.name, updatedAt: item.last_message_at ?? undefined })) : [])
      publishSearchSource(userId, 'journals', journals.status === 'fulfilled' ? journals.value.map((item) => ({ kind: 'journal', id: item.id, title: item.title, updatedAt: item.updated_at })) : [], true)
    })
    .finally(() => pending.delete(userId))
  pending.set(userId, request)
  return request
}
