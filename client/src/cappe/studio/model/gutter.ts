// The gutter: where facing pages meet at the spine, the binding swallows a
// strip either side of it. The Studio shades that strip (View → Gutter
// safety) and the issue board says when words run into it, so nobody finds
// out from a printed copy. Pictures may cross it: a picture across a spread
// is meant to (model/crops.ts keeps its two halves lined up).

import { spreads } from './doc'
import { inheritedItems, wordedFrames } from './rhythm'
import type { Doc } from './types'

/** How wide the strip is on each side of the spine, in pt (a quarter inch). */
export const GUTTER_SAFE = 18

/** How far a picture split clear of the spine stops short of it on each page:
 *  past the strip, so the fold is plainly white. */
export const SPINE_CLEAR = GUTTER_SAFE * 2

export type GutterIssue = { page: number; item: string; message: string }

/** Text frames with words in them that reach into the strip (or across
 *  the spine), on facing pages. */
export function gutterIssues(doc: Doc): GutterIssue[] {
  if (!doc.facing) return []
  const w = doc.size.w
  const worded = wordedFrames(doc)
  const out: GutterIssue[] = []
  const index = new Map(doc.pages.map((p, i) => [p.id, i]))
  const paired = new Set(spreads(doc).filter((s) => s.length === 2).flat())
  for (const item of [...inheritedItems(doc).items, ...doc.items]) {
    if (item.kind !== 'text' || item.hidden || !worded.has(item.id)) continue
    const i = index.get(item.page)
    if (i === undefined || !paired.has(i)) continue
    const left = i % 2 === 1
    const reaches = left ? item.x + item.w > w - GUTTER_SAFE : item.x < GUTTER_SAFE
    if (!reaches) continue
    const crosses = left ? item.x + item.w > w : item.x < 0
    out.push({ page: i, item: item.id, message: crosses
      ? `Words on page ${i + 1} cross the spine.`
      : `Words on page ${i + 1} run into the gutter, where the binding hides them.` })
  }
  return out.sort((a, b) => a.page - b.page)
}
