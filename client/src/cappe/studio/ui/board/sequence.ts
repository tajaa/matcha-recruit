// What the issue board moves and where a drag drops it.

import { linkGroups } from '../../model/crops'
import { spreads } from '../../model/doc'
import { moveBlock } from '../../model/sections'
import type { Doc } from '../../model/types'

/** Pages that have to move with their facing page: a picture runs across
 *  the spine (linked frames on both, or a frame hanging over onto the
 *  other), so splitting them would cut it in two. */
export function boundPages(doc: Doc, ids: Iterable<string>): string[] {
  const want = new Set(ids)
  const w = doc.size.w
  const facingOf = new Map<string, string>()
  for (const pages of spreads(doc)) {
    if (pages.length !== 2) continue
    const [l, r] = pages.map((p) => doc.pages[p].id)
    const across = doc.items.some((i) => (i.page === l && i.x + i.w > w + 0.5) || (i.page === r && i.x < -0.5))
      || linkGroups(doc).some((g) => g.members.some((m) => m.page === l) && g.members.some((m) => m.page === r))
    if (across) { facingOf.set(l, r); facingOf.set(r, l) }
  }
  for (const id of [...want]) { const f = facingOf.get(id); if (f) want.add(f) }
  return doc.pages.filter((p) => want.has(p.id)).map((p) => p.id)
}

/** A page tile on the board: its index and where it is on screen. */
export type Tile = { index: number; left: number; top: number; right: number; bottom: number }

/** Where a drop at (x, y) puts pages: before the tile it's on (its left
 *  half) or after it, else beside the nearest tile in that row; whether that
 *  was before it (the pages then join that page's story); and where to draw
 *  the bar that says so. null when there are no tiles. */
export function slotAt(tiles: Tile[], x: number, y: number):
  { slot: number; before: boolean; x: number; top: number; bottom: number } | null {
  if (!tiles.length) return null
  const row = tiles.filter((t) => y >= t.top && y <= t.bottom)
  const near = (row.length ? row : tiles).reduce((best, t) => {
    const dx = x < t.left ? t.left - x : x > t.right ? x - t.right : 0
    const dy = y < t.top ? t.top - y : y > t.bottom ? y - t.bottom : 0
    const d = dx * dx + dy * dy
    return d < best.d ? { t, d } : best
  }, { t: tiles[0], d: Infinity }).t
  const before = x < (near.left + near.right) / 2
  return { slot: before ? near.index : near.index + 1, before, x: before ? near.left : near.right, top: near.top, bottom: near.bottom }
}

/** Pages moved one step earlier (-1) or later (1): a spread's width with
 *  facing pages, so the pages around them keep their sides. */
export function nudge(doc: Doc, ids: string[], dir: -1 | 1): Doc {
  const at = ids.map((id) => doc.pages.findIndex((p) => p.id === id)).filter((i) => i !== -1).sort((a, b) => a - b)
  if (!at.length) return doc
  const step = doc.facing ? 2 : 1
  const slot = dir < 0 ? Math.max(0, at[0] - step) : Math.min(doc.pages.length, at[at.length - 1] + 1 + step)
  return moveBlock(doc, ids, slot)
}

/** Whether a move turned pages over (a left page now a right one): an odd
 *  number of pages moved with facing pages on. Says from which page. */
export function sidesChanged(before: Doc, after: Doc): number | null {
  if (!after.facing || before.pages === after.pages) return null
  const was = new Map(before.pages.map((p, i) => [p.id, i % 2]))
  const k = after.pages.findIndex((p, i) => was.get(p.id) !== i % 2)
  return k === -1 ? null : k
}
