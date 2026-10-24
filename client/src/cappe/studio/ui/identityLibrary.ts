import { useSyncExternalStore } from 'react'
import { identityApi, type SavedIdentity } from '../identityApi'
import type { MagazineIdentity } from '../model/types'
import type { Store } from '../store/store'

type State = SavedIdentity & { loading: boolean; ready: boolean; pending: boolean; error: string | null; message: string | null }
const problem = (e: unknown) => e instanceof Error ? e.message : 'The magazine identity couldn’t be saved. Try again.'
class IdentityLibrary {
  private state: State = { rev: 0, identity: null, loading: true, ready: false, pending: false, error: null, message: null }
  private listeners = new Set<() => void>()
  private generation = 0
  private reading: Promise<void> | null = null
  private writeError: string | null = null
  private siteId: string
  constructor(siteId: string) { this.siteId = siteId }
  get = () => this.state
  subscribe = (f: () => void) => { this.listeners.add(f); return () => { this.listeners.delete(f) } }
  private set(patch: Partial<State>) { this.state = { ...this.state, ...patch }; this.listeners.forEach((f) => f()) }
  async load(clearError = false): Promise<void> {
    if (this.state.pending) return
    if (this.reading) return this.reading
    if (clearError) this.writeError = null
    const generation = ++this.generation
    this.set({ loading: true, error: this.writeError })
    this.reading = identityApi.open(this.siteId).then((saved) => {
      if (generation === this.generation) this.set({ ...saved, ready: true })
    }, (e) => { if (generation === this.generation) this.set({ error: this.writeError ?? problem(e) }) })
      .finally(() => { if (generation === this.generation) { this.reading = null; this.set({ loading: false }) } })
    return this.reading
  }
  async save(identity: MagazineIdentity): Promise<void> {
    if (!this.state.ready || this.state.pending) return
    this.generation++; this.reading = null; this.writeError = null
    this.set({ pending: true, loading: false, error: null, message: null })
    const snapshot = structuredClone(identity)
    for (const p of snapshot.parents) for (const t of p.threads) delete t.comp
    try {
      const saved = await identityApi.save(this.siteId, snapshot, this.state.rev)
      this.set({ ...saved, message: 'Magazine identity saved. Other issues keep their design until you choose to use this identity.' })
    } catch (e) { this.writeError = problem(e); this.set({ error: this.writeError }) } finally { this.set({ pending: false }) }
  }
}
const libraries = new WeakMap<Store, IdentityLibrary>()
export function identityLibrary(store: Store, siteId: string) {
  let library = libraries.get(store)
  if (!library) { library = new IdentityLibrary(siteId); libraries.set(store, library) }
  return library
}
export function useIdentityLibrary(store: Store, siteId: string) {
  const library = identityLibrary(store, siteId)
  return useSyncExternalStore(library.subscribe, library.get, library.get)
}
