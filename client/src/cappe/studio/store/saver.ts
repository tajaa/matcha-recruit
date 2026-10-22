// Saving a paged story as it is designed: a moment after each change
// (autosave), or now (⌘S keeps a version; "Update live story" publishes).
// Each save names the revision it started from; one made elsewhere since
// stops saving here until the story is reloaded.

import { CappeApiError } from '../../api'
import { studioApi } from '../api'
import type { Store } from './store'

const AUTOSAVE_MS = 1500

export class Saver {
  private pending: Promise<void> | null = null
  private timer = 0
  private store: Store
  private siteId: string
  private postId: string

  constructor(store: Store, siteId: string, postId: string) {
    this.store = store
    this.siteId = siteId
    this.postId = postId
    store.onDocChange = () => this.schedule()
  }

  schedule(): void {
    window.clearTimeout(this.timer)
    this.timer = window.setTimeout(() => void this.save(), AUTOSAVE_MS)
  }

  dispose(): void {
    window.clearTimeout(this.timer)
    this.store.onDocChange = null
  }

  /** Whether leaving now would lose changes. */
  unsaved(): boolean {
    const st = this.store.get().save.state
    return st === 'dirty' || st === 'saving' || st === 'error'
  }

  async save({ keep = false, publish = false }: { keep?: boolean; publish?: boolean } = {}): Promise<void> {
    window.clearTimeout(this.timer)
    while (this.pending) await this.pending
    const { store } = this
    const s = store.get()
    if (s.save.state === 'conflict') {
      if (publish) throw new Error('This story was saved somewhere else. Reload it first.')
      return
    }
    if (s.save.state === 'saved' && !keep && !publish) return
    store.set({ save: { ...s.save, state: 'saving' } })
    const sent = s.doc
    let failure: unknown = null
    this.pending = studioApi.save(this.siteId, this.postId, { base_rev: s.save.rev, doc: sent, keep, publish }).then((res) => {
      store.set((x) => ({ save: { ...x.save, rev: res.rev, draft: res.draft, state: x.doc === sent ? 'saved' : 'dirty', message: null } }))
    }, (err) => {
      failure = err
      const stale = err instanceof CappeApiError && err.code === 'stale_rev'
      store.set((x) => ({ save: { ...x.save, state: stale ? 'conflict' : 'error', message: err instanceof Error ? err.message : null } }))
    }).finally(() => { this.pending = null })
    await this.pending
    if (failure && publish) throw failure
    if (store.get().save.state === 'dirty') this.schedule()
  }
}
