import { useCallback, useSyncExternalStore } from 'react'

export type StarKind = 'channels' | 'journals' | 'files'
export type StarredFileMeta = { id: string; projectId: string; name: string; url: string }

const EMPTY: string[] = []
const cache = new Map<string, string[]>()
const changedEvent = 'matcha-work:stars-changed'

function key(userId: string, kind: StarKind) { return `mw-starred-${kind}:${userId}` }
function fileMetaKey(userId: string) { return `mw-starred-file-meta:${userId}` }
export function safeFileHref(url: string): boolean { return /^https?:\/\//i.test(url) || (url.startsWith('/') && !url.startsWith('//')) }

export function getStarIds(userId: string | null | undefined, kind: StarKind): string[] {
  if (!userId) return EMPTY
  const storageKey = key(userId, kind)
  const cached = cache.get(storageKey)
  if (cached) return cached
  let ids: string[] = []
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(storageKey) ?? '[]')
    if (Array.isArray(parsed)) ids = parsed.filter((value): value is string => typeof value === 'string')
  } catch { /* Storage can be unavailable in private browsing. */ }
  cache.set(storageKey, ids)
  return ids
}

export function getStarredFileMeta(userId: string | null | undefined): StarredFileMeta[] {
  if (!userId) return []
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(fileMetaKey(userId)) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((value): value is StarredFileMeta =>
      !!value && typeof value === 'object' && typeof value.id === 'string'
      && typeof value.name === 'string' && typeof value.url === 'string' && safeFileHref(value.url)
      && typeof value.projectId === 'string') : []
  } catch { return [] }
}

export function toggleStar(userId: string | null | undefined, kind: StarKind, id: string, file?: StarredFileMeta): boolean {
  if (!userId) return false
  const storageKey = key(userId, kind)
  const current = getStarIds(userId, kind)
  const starred = !current.includes(id)
  const next = starred ? [...current, id] : current.filter((value) => value !== id)
  try {
    if (kind === 'files') {
      const oldMeta = getStarredFileMeta(userId)
      const nextMeta = starred && file ? [...oldMeta.filter((item) => item.id !== id), file]
        : oldMeta.filter((item) => item.id !== id)
      localStorage.setItem(fileMetaKey(userId), JSON.stringify(nextMeta))
    }
    localStorage.setItem(storageKey, JSON.stringify(next))
  } catch { return false }
  cache.set(storageKey, next)
  window.dispatchEvent(new CustomEvent(changedEvent, { detail: storageKey }))
  return starred
}

export function useStars(userId: string | null | undefined, kind: StarKind) {
  const subscribe = useCallback((listener: () => void) => {
    const storageKey = userId ? key(userId, kind) : ''
    const onChanged = (event: Event) => { if ((event as CustomEvent<string>).detail === storageKey) listener() }
    const onStorage = (event: StorageEvent) => {
      if (event.key === storageKey) { cache.delete(storageKey); listener() }
    }
    window.addEventListener(changedEvent, onChanged)
    window.addEventListener('storage', onStorage)
    return () => { window.removeEventListener(changedEvent, onChanged); window.removeEventListener('storage', onStorage) }
  }, [userId, kind])
  const snapshot = useCallback(() => getStarIds(userId, kind), [userId, kind])
  return useSyncExternalStore(subscribe, snapshot, () => EMPTY)
}

export function clearStarCache() { cache.clear() }
