// The subject in front of the lettering, for covers: a photo stays behind the
// masthead, and a second frame over the text shows the photo's cut-out
// (Picture Editor → Cut out) at exactly the same place, linked to it
// (model/crops.ts), so the model stands in front of the letters it covers.
// Shrinking that frame limits which letters the subject covers; moving the
// photo's crop moves both. The partner prints no credit (the photo's does)
// and is clicked only on the subject itself (canvas/geometry.ts).

import { allIds, newId } from './doc'
import type { Asset, Doc, ImageItem, Item, Shape } from './types'

/** Whether a library picture is a cut-out (a Picture Editor edit with one). */
export const isCutout = (a: Asset | undefined): boolean => !!a && a.kind === 'edit' && !!a.recipe?.cutout

/** The cut-out to set in front of a frame's picture: the picture itself when
 *  it is one (its photo is its parent), else the newest cut-out made of it. */
export function cutoutFor(assets: Record<string, Asset>, assetId: string | null): Asset | null {
  if (!assetId) return null
  const own = assets[assetId]
  if (isCutout(own)) return own!.parent && assets[own!.parent] ? own! : null
  const made = Object.values(assets).filter((a) => isCutout(a) && a.parent === assetId)
  return made.length ? made[made.length - 1] : null
}

const overlaps = (a: Item, b: Item) => a.page === b.page && a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h

/** Why the subject can't be put in front of this frame's picture, or null. */
export function subjectProblem(doc: Doc, id: string): string | null {
  const item = doc.items.find((i) => i.id === id)
  if (!item || item.kind !== 'image' || !item.asset_id) return 'Select a picture frame with a photo in it.'
  if (item.cutout) return 'This frame is already the subject in front.'
  if (item.locked) return 'Unlock the frame first.'
  if (item.rot) return 'A turned frame can’t have the subject in front.'
  if (item.fit !== 'fill') return 'Set the picture to Fill first.'
  return null
}

/** The photo in frame `id` kept behind the text it overlaps, and a linked
 *  frame over that text showing `cutout` (its silhouette `shape`). Returns
 *  the partner's id. */
export function putSubjectInFront(doc: Doc, id: string, cutout: Asset, shape: Shape): { doc: Doc; id: string } | null {
  if (subjectProblem(doc, id) || !cutout.parent) return null
  const photo = doc.items.find((i): i is ImageItem => i.id === id && i.kind === 'image')!
  const taken = doc.items.flatMap((i) => (i.kind === 'image' && i.link ? [i.link] : []))
  const link = photo.link ?? newId('lk', taken)
  const partnerId = newId('i', allIds(doc))
  const base: ImageItem = { ...photo, asset_id: cutout.parent, link, shape }
  const partner: ImageItem = { ...photo, id: partnerId, asset_id: cutout.id, link, cutout: true, shape, caption: '', fill: null,
    stroke: null, locked: false, hidden: false, name: 'Subject in front' }
  delete partner.wrap
  delete partner.fill_swatch
  delete partner.stroke_swatch
  const rest = doc.items.filter((i) => i.id !== id)
  const texts = rest.map((i, k) => [i, k] as const).filter(([i]) => i.kind === 'text' && !i.hidden && overlaps(i, photo))
  // The photo goes under the lowest text it overlaps (if it was over it), the
  // cut-out over the highest.
  const at = doc.items.findIndex((i) => i.id === id)
  const under = texts.length ? Math.min(at, texts[0][1]) : at
  const items = [...rest.slice(0, under), base, ...rest.slice(under)]
  const over = texts.length ? items.findIndex((i) => i.id === texts[texts.length - 1][0].id) + 1 : items.indexOf(base) + 1
  items.splice(over, 0, partner)
  return { doc: { ...doc, items }, id: partnerId }
}
