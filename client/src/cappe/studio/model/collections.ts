import { CUSTOM_FAMILY, mergeRuns, sparsePara } from './doc'
import { detachParent, resolveItem, resolvedThreads } from './identity'
import type { Doc, Item } from './types'

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

/** The pages as they look, with nothing that names this story's magazine
 *  identity: a collection goes into other stories, whose identities don't
 *  have these styles, swatches or parents (and a reference to one they lack
 *  makes the story unsavable). Parent frames become the page's own. */
export function flattenIdentity(doc: Doc): Doc {
  if (!doc.identity) return doc
  let flat = doc
  doc.pages.forEach((p, k) => { if (p.parent) flat = detachParent(flat, k) })
  const identity = flat.identity
  const out: Doc = { ...flat,
    pages: flat.pages.map((p) => ({ id: p.id })),
    threads: resolvedThreads(flat).map((t) => ({ ...t, paras: t.paras.map((p) => ({ ...sparsePara(p), runs: mergeRuns(p.runs) })) })),
    items: flat.items.map((i) => {
      const resolved: Item = { ...resolveItem(i, identity) }
      delete resolved.fill_swatch
      delete resolved.stroke_swatch
      return resolved
    }),
  }
  delete out.identity
  return out
}

/** A portable snapshot: source photos, reader access, the source's identity
 *  references and its magazine's own fonts stay with the story (as the
 *  server's collection_doc: a cut-out subject is its photo's, and text in an
 *  own font is set in the default face). */
export function portableCollection(source: Doc): Doc {
  const doc = flattenIdentity(source)
  const out: Doc = structuredClone({ ...doc, paywall_page: null,
    items: doc.items.map((i) => {
      if (i.kind !== 'image') return i
      const plain = { ...i, asset_id: null, caption: '' }
      delete plain.cutout
      delete plain.shape
      if (plain.wrap?.m === 'subject') plain.wrap = { ...plain.wrap, m: 'box' }
      return plain
    }),
    threads: doc.threads.map((t) => ({ id: t.id, frames: t.frames, paras: t.paras.map((p) => ({ ...p,
      runs: mergeRuns(p.runs.map((r) => {
        if (!r.font || !CUSTOM_FAMILY.test(r.font)) return r
        const rest = { ...r }
        delete rest.font
        return rest
      })) })) })),
  })
  delete out.faces
  return out
}
