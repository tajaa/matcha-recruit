import { composeDoc } from '../../compose/compose'
import type { Doc } from '../../model/types'
import type { Store } from '../../store/store'
import type { StudioCtx } from '../context'

// All page thumbnails share one font load and composition, including across
// panel remounts. Both cache keys are weak: closing a story releases its work.
const previews = new WeakMap<Store, WeakMap<Doc, Promise<Doc>>>()

export function collectionPreview(c: StudioCtx, doc: Doc): Promise<Doc> {
  let documents = previews.get(c.store)
  if (!documents) { documents = new WeakMap(); previews.set(c.store, documents) }
  const cache = documents
  const hit = cache.get(doc)
  if (hit) return hit
  const prepared = c.fonts.ensureDoc(doc).then(() => composeDoc(doc, c.store.measure, true).doc)
  cache.set(doc, prepared)
  // A missing font can be loaded on retry; never cache a permanent failure.
  prepared.catch(() => cache.delete(doc))
  return prepared
}
