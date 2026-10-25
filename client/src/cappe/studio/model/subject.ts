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

const canon = (v: unknown): string => Array.isArray(v) ? `[${v.map(canon).join(',')}]`
  : v && typeof v === 'object' ? `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${canon((v as Record<string, unknown>)[k])}`).join(',')}}`
    : JSON.stringify(v)

/** What an edit did besides its cut-out (its crop, turn, flip and look), as a key. */
function unmaskedKey(a: Asset): string {
  const rest: Record<string, unknown> = { ...(a.recipe ?? {}) }
  delete rest.cutout
  return canon(rest)
}

/** The picture behind a cut-out: its photo as it was when cut out, so the two
 *  line up pixel for pixel. The photo itself when the cut-out did nothing
 *  else to it, else an edit of it made the same way without the cut-out
 *  (the Picture Editor saves one with it); null when there is none. */
export function backingFor(assets: Record<string, Asset>, cutout: Asset): string | null {
  if (!isCutout(cutout) || !cutout.parent) return null
  const key = unmaskedKey(cutout)
  if (key === '{}') return cutout.parent
  const same = Object.values(assets).filter((a) => a.kind === 'edit' && !isCutout(a) && a.parent === cutout.parent && unmaskedKey(a) === key)
  return same.length ? same[same.length - 1].id : null
}

/** The cut-out to set in front of a frame's picture: the picture itself when
 *  it is one (with a picture to go behind it), else the newest cut-out made
 *  of exactly that picture. */
export function cutoutFor(assets: Record<string, Asset>, assetId: string | null): Asset | null {
  if (!assetId) return null
  const own = assets[assetId]
  if (isCutout(own)) return backingFor(assets, own!) ? own! : null
  const made = Object.values(assets).filter((a) => isCutout(a) && backingFor(assets, a) === assetId)
  return made.length ? made[made.length - 1] : null
}

/** A cut-out frame set over its photo (the subject in front, server
 *  schema.is_partner) while that photo is there: one whose photo was deleted
 *  or hidden is a picture of its own, credit and all. */
export function isPartner(item: Item, items: Item[]): item is ImageItem {
  if (item.kind !== 'image' || !item.cutout || !item.link) return false
  return items.some((o) => o !== item && o.kind === 'image' && o.link === item.link && !o.cutout && !o.hidden)
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

/** The photo in frame `id` kept behind the text it overlaps (as `backing`,
 *  backingFor: the picture the cut-out lines up with), and a linked frame
 *  over that text showing `cutout` (its silhouette `shape`). Returns the
 *  partner's id. */
export function putSubjectInFront(doc: Doc, id: string, cutout: Asset, shape: Shape, backing: string): { doc: Doc; id: string } | null {
  if (subjectProblem(doc, id) || !isCutout(cutout)) return null
  const photo = doc.items.find((i): i is ImageItem => i.id === id && i.kind === 'image')!
  const taken = doc.items.flatMap((i) => (i.kind === 'image' && i.link ? [i.link] : []))
  const link = photo.link ?? newId('lk', taken)
  const partnerId = newId('i', allIds(doc))
  const base: ImageItem = { ...photo, asset_id: backing, link, shape }
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
