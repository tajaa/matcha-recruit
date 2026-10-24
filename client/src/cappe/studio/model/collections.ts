import type { Doc } from './types'

export type CollectionCard = { id: string; name: string; page_count: number; created_at: string }
export type SavedCollection = CollectionCard & { doc: Doc }
/** A built-in collection; `pages` names each page ("Cover", "Contents"…), in order. */
export type EditorialCollection = { id: string; name: string; direction: string; description: string; fonts: string; pages: string[]; doc: Doc }

export const COLLECTION_LIMITS = { pages: 32, bytes: 1_000_000, count: 50 } as const

/** Python's compact ensure_ascii JSON size. Studio measurements are rounded
 *  to hundredths; the normalized document has no exponent-sized numbers. */
export function collectionJsonSize(value: unknown): number {
  return JSON.stringify(value).replace(/[\u007f-\uffff]/g, (ch) => `\\u${ch.charCodeAt(0).toString(16).padStart(4, '0')}`).length
}

/** A portable snapshot: source photos and reader access stay with the story. */
export function portableCollection(doc: Doc): Doc {
  return structuredClone({ ...doc, paywall_page: null,
    items: doc.items.map((i) => i.kind === 'image' ? { ...i, asset_id: null, caption: '' } : i),
    threads: doc.threads.map((t) => ({ id: t.id, frames: t.frames, paras: t.paras })),
  })
}
