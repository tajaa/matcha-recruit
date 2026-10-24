// Like Ask the Studio's conversation, a library operation belongs to the
// Studio session. Hiding or changing a panel cannot lose an in-flight result.
import { useSyncExternalStore } from 'react'
import { CappeApiError } from '../../../api'
import { collectionsApi } from '../../collectionsApi'
import { COLLECTION_LIMITS, collectionJsonSize, portableCollection, type CollectionCard } from '../../model/collections'
import type { Doc } from '../../model/types'
import type { Store } from '../../store/store'

type LibraryState = {
  rows: CollectionCard[]; loading: boolean; pending: 'save' | 'remove' | null
  error: string | null; message: string | null; saving: boolean; name: string
}
const message = (e: unknown) => e instanceof Error && e.message ? e.message : 'The collection couldn’t be saved. Try again.'

export class CollectionLibrary {
  private state: LibraryState = { rows: [], loading: true, pending: null, error: null, message: null, saving: false, name: '' }
  private listeners = new Set<() => void>()
  private loaded = false
  private generation = 0
  private reading: Promise<void> | null = null
  private retry: { key: string; signature: string; doc: Doc } | null = null
  private mutationError: string | null = null

  get = () => this.state
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn) } }
  private set(patch: Partial<LibraryState>) { this.state = { ...this.state, ...patch }; this.listeners.forEach((fn) => fn()) }
  feedback = () => { this.mutationError = null; this.set({ error: null, message: null }) }
  form = (saving: boolean) => { this.mutationError = null; this.set({ saving, error: null }) }
  rename = (name: string) => this.set({ name })

  load(refresh = false): Promise<void> {
    if (this.state.pending || (this.loaded && !refresh)) return Promise.resolve()
    if (this.reading) return this.reading
    const generation = ++this.generation
    // Reopening refreshes cards, but must still show a write that failed
    // while the panel was hidden. Explicit feedback/retry clears it.
    this.set({ loading: true, error: this.mutationError })
    const read = collectionsApi.list().then((rows) => {
      if (generation !== this.generation) return
      this.loaded = true
      this.set({ rows })
    }, (e) => { if (generation === this.generation) this.set({ error: this.mutationError ?? message(e) }) })
      .finally(() => {
        if (generation === this.generation) { this.reading = null; this.set({ loading: false }) }
      })
    this.reading = read
    return read
  }

  private begin(pending: 'save' | 'remove'): boolean {
    if (this.state.pending) return false
    // A GET started before this mutation may never replace its result.
    this.generation++
    this.reading = null
    this.mutationError = null
    this.set({ pending, loading: false, error: null, message: null })
    return true
  }

  async save(raw: Doc): Promise<void> {
    const name = this.state.name.trim()
    if (!name || !this.begin('save')) return
    let saved = false
    try {
      const doc = portableCollection(raw)
      if (doc.pages.length > COLLECTION_LIMITS.pages) throw new Error(`Save up to ${COLLECTION_LIMITS.pages} pages in one collection.`)
      if (collectionJsonSize(doc) > COLLECTION_LIMITS.bytes) throw new Error('A collection is too big to save. Use fewer pages or less text.')
      const signature = JSON.stringify([name, doc])
      if (this.retry?.signature !== signature) this.retry = { key: crypto.randomUUID(), signature, doc }
      const row = await collectionsApi.save(name, this.retry.doc, this.retry.key)
      this.retry = null
      saved = true
      this.set({ rows: [row, ...this.state.rows.filter((r) => r.id !== row.id)], saving: false, name: '',
        message: `“${row.name}” saved to your collections.` })
    } catch (e) { this.mutationError = message(e); this.set({ error: this.mutationError }) } finally {
      this.set({ pending: null })
      // A successful mutation cannot stand in for a library read that failed.
      if (saved && !this.loaded) void this.load(true)
    }
  }

  async remove(id: string): Promise<boolean> {
    if (!this.begin('remove')) return false
    try {
      try { await collectionsApi.remove(id) } catch (e) {
        // Also works with the older server after a lost successful response.
        if (!(e instanceof CappeApiError && e.status === 404)) throw e
      }
      this.set({ rows: this.state.rows.filter((r) => r.id !== id),
        message: 'Collection removed from your library. Pages already added to stories stay there.' })
      return true
    } catch (e) { this.mutationError = message(e); this.set({ error: this.mutationError }); return false } finally { this.set({ pending: null }) }
  }
}

const libraries = new WeakMap<Store, CollectionLibrary>()
export function collectionLibrary(store: Store): CollectionLibrary {
  let library = libraries.get(store)
  if (!library) { library = new CollectionLibrary(); libraries.set(store, library) }
  return library
}
export function useCollectionLibrary(store: Store) {
  const library = collectionLibrary(store)
  return useSyncExternalStore(library.subscribe, library.get, library.get)
}
