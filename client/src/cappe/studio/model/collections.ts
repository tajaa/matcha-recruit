import type { Doc } from './types'

export type CollectionCard = { id: string; name: string; page_count: number; created_at: string }
export type SavedCollection = CollectionCard & { doc: Doc }
export type EditorialCollection = { id: string; name: string; direction: string; description: string; fonts: string; doc: Doc }

export const COLLECTION_LIMITS = { pages: 32, bytes: 1_000_000, count: 50 } as const

/** A portable snapshot: source photos and reader access stay with the story. */
export function portableCollection(doc: Doc): Doc {
  return structuredClone({ ...doc, paywall_page: null,
    items: doc.items.map((i) => i.kind === 'image' ? { ...i, asset_id: null, caption: '' } : i),
    threads: doc.threads.map((t) => ({ id: t.id, frames: t.frames, paras: t.paras })),
  })
}
