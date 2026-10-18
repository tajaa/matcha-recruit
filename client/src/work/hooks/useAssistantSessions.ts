import { useCallback, useEffect, useState } from 'react'
import {
  archiveAssistantConversation, createAssistantConversation, listAssistantConversations,
  renameAssistantConversation, restoreAssistantConversation, type AssistantConversation,
} from '../api/matchaWork/assistant'
import { apiErrorText } from '../utils/apiErrorText'

type Page = { items: AssistantConversation[]; hasMore: boolean }

const EMPTY: Page = { items: [], hasMore: false }

/** The person's sessions with Espresso, as the Mac's session picker keeps
 *  them: the active list (loaded on open), archived ones (loaded when first
 *  asked for), and the changes the rail makes. Every change updates the lists
 *  in place from what the server returned; nothing is guessed. */
export function useAssistantSessions() {
  const [active, setActive] = useState<Page | null>(null)
  const [archived, setArchived] = useState<Page | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (which: 'active' | 'archived', offset = 0) => {
    const out = await listAssistantConversations(offset, which === 'archived')
    const set = which === 'archived' ? setArchived : setActive
    set((prev) => {
      const kept = offset && prev ? prev.items : []
      const seen = new Set(kept.map((c) => c.id))
      return { items: [...kept, ...out.conversations.filter((c) => !seen.has(c.id))], hasMore: out.has_more }
    })
  }, [])

  const run = useCallback(async <T,>(work: () => Promise<T>, fallback: string): Promise<T | null> => {
    setBusy(true)
    setError(null)
    try {
      return await work()
    } catch (e) {
      setError(apiErrorText(e, fallback))
      return null
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    listAssistantConversations(0, false)
      .then((out) => { if (!cancelled) setActive({ items: out.conversations, hasMore: out.has_more }) })
      .catch((e: unknown) => {
        if (cancelled) return
        setActive(EMPTY)
        setError(apiErrorText(e, "Couldn't load your sessions."))
      })
    return () => { cancelled = true }
  }, [])

  const loadMore = useCallback((which: 'active' | 'archived') => {
    const page = which === 'archived' ? archived : active
    return run(() => load(which, page?.items.length ?? 0), "Couldn't load more sessions.")
  }, [active, archived, load, run])

  const loadArchived = useCallback(() => {
    if (archived) return Promise.resolve(null)
    return run(() => load('archived'), "Couldn't load archived sessions.")
  }, [archived, load, run])

  /** Resolves to the new session's id, or null when it failed (the error is set). */
  const create = useCallback((title: string, requestId: string) => run(async () => {
    const { channel_id } = await createAssistantConversation(title, requestId)
    await load('active')
    return channel_id
  }, "Couldn't start a new session."), [load, run])

  const rename = useCallback((id: string, title: string) => run(async () => {
    const out = await renameAssistantConversation(id, title)
    const swap = (page: Page | null) => page && { ...page, items: page.items.map((c) => (c.id === id ? out : c)) }
    setActive(swap)
    setArchived(swap)
    return out
  }, "Couldn't rename that session."), [run])

  const archive = useCallback((id: string) => run(async () => {
    const out = await archiveAssistantConversation(id)
    setActive((page) => page && { ...page, items: page.items.filter((c) => c.id !== id) })
    // Archived is ordered like the active list: by when it was last used.
    setArchived((page) => page && { ...page, items: sortByUse([out, ...page.items]) })
    return out
  }, "Couldn't archive that session."), [run])

  const restore = useCallback((id: string) => run(async () => {
    const out = await restoreAssistantConversation(id)
    setArchived((page) => page && { ...page, items: page.items.filter((c) => c.id !== id) })
    setActive((page) => page && { ...page, items: sortByUse([out, ...page.items]) })
    return out
  }, "Couldn't restore that session."), [run])

  return {
    sessions: active?.items ?? [],
    hasMore: active?.hasMore ?? false,
    loaded: active !== null,
    archived: archived?.items ?? null,
    archivedHasMore: archived?.hasMore ?? false,
    busy,
    error,
    clearError: () => setError(null),
    loadMore,
    loadArchived,
    create,
    rename,
    archive,
    restore,
  }
}

export type AssistantSessions = ReturnType<typeof useAssistantSessions>

function sortByUse(items: AssistantConversation[]) {
  return [...items].sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? '') || b.id.localeCompare(a.id))
}
