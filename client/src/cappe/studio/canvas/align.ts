// Lining things up: several to the box around them, one to its page, and
// three or more spaced evenly. Worked out on the pasteboard, so things on
// both pages of a spread line up with each other; anything whose middle
// lands on the other page goes onto it, as a drag would put it there.

import { round } from '../model/limits'
import { updateItems } from '../model/ops'
import type { Doc, Item } from '../model/types'
import { bounds, centre, itemBox, layout, pageAt, type Layout, type Pt, type Rect } from './geometry'

export type Align = 'left' | 'centre' | 'right' | 'top' | 'middle' | 'bottom'
export type Spread = 'across' | 'down'

const originOf = (doc: Doc, lay: Layout) => (i: Item): Pt => lay.origin[doc.pages.findIndex((p) => p.id === i.page)]

/** The items that would move: selected, there, and not locked. */
const movable = (doc: Doc, ids: readonly string[]) => doc.items.filter((i) => ids.includes(i.id) && !i.locked)

/** Each item onto the page under its middle (where it is already, mostly). */
export function rehome(doc: Doc, lay: Layout, ids: Iterable<string>): Doc {
  let next = doc
  for (const id of ids) {
    const item = next.items.find((i) => i.id === id)
    if (!item) continue
    const at = next.pages.findIndex((p) => p.id === item.page)
    const o = lay.origin[at]
    if (!o) continue
    const to = pageAt(next, lay, centre(itemBox(item, o)))
    if (to === at) continue
    const pid = next.pages[to].id, no = lay.origin[to]
    next = updateItems(next, [id], (i) => ({ ...i, page: pid, x: round(i.x + o.x - no.x), y: round(i.y + o.y - no.y) }))
  }
  return next
}

/** Move each item by its own amount (pasteboard points), then rehome them. */
function shift(doc: Doc, lay: Layout, moves: Map<string, Pt>): Doc {
  const moved = updateItems(doc, moves.keys(), (i) => {
    const d = moves.get(i.id)!
    const x = round(i.x + d.x), y = round(i.y + d.y)
    // Already there (to the hundredth of a point the document keeps): no undo step.
    return x === i.x && y === i.y ? i : { ...i, x, y }
  })
  return moved === doc ? doc : rehome(moved, lay, moves.keys())
}

/** Line the items up: one with its page, several with the box around all of
 *  them (locked ones stay put but count). A turned item lines up by the box
 *  around its corners. */
export function alignItems(doc: Doc, ids: readonly string[], how: Align): Doc {
  const lay = layout(doc)
  const origin = originOf(doc, lay)
  const chosen = doc.items.filter((i) => ids.includes(i.id))
  const items = movable(doc, ids)
  if (!items.length) return doc
  let target: Rect | null
  if (chosen.length === 1) {
    const o = origin(chosen[0])
    target = o ? { x: o.x, y: o.y, w: doc.size.w, h: doc.size.h } : null
  } else target = bounds(chosen, origin)
  if (!target) return doc
  const moves = new Map<string, Pt>()
  for (const i of items) {
    const b = bounds([i], origin)!
    const dx = how === 'left' ? target.x - b.x : how === 'centre' ? target.x + target.w / 2 - (b.x + b.w / 2)
      : how === 'right' ? target.x + target.w - (b.x + b.w) : 0
    const dy = how === 'top' ? target.y - b.y : how === 'middle' ? target.y + target.h / 2 - (b.y + b.h / 2)
      : how === 'bottom' ? target.y + target.h - (b.y + b.h) : 0
    moves.set(i.id, { x: dx, y: dy })
  }
  return shift(doc, lay, moves)
}

/** Whether `spaceItems` can space these out: three or more that can move. */
export const canSpace = (doc: Doc, ids: readonly string[]) => movable(doc, ids).length >= 3

/** Even gaps between three or more items, across or down: the first and the
 *  last stay where they are, the rest move between them. */
export function spaceItems(doc: Doc, ids: readonly string[], how: Spread): Doc {
  if (!canSpace(doc, ids)) return doc
  const lay = layout(doc)
  const origin = originOf(doc, lay)
  const across = how === 'across'
  const boxes = movable(doc, ids).map((i) => ({ id: i.id, b: bounds([i], origin)! }))
    .sort((a, b) => (across ? a.b.x - b.b.x : a.b.y - b.b.y))
  const start = (r: Rect) => (across ? r.x : r.y)
  const size = (r: Rect) => (across ? r.w : r.h)
  const first = boxes[0].b, last = boxes[boxes.length - 1].b
  const span = start(last) + size(last) - start(first)
  const gap = (span - boxes.reduce((n, x) => n + size(x.b), 0)) / (boxes.length - 1)
  const moves = new Map<string, Pt>()
  let at = start(first)
  for (const { id, b } of boxes) {
    const d = at - start(b)
    moves.set(id, across ? { x: d, y: 0 } : { x: 0, y: d })
    at += size(b) + gap
  }
  return shift(doc, lay, moves)
}
