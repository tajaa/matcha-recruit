// Where the bar over the selection goes, and when it shows (`SelectionBar.tsx`).

import type { Rect } from '../canvas/geometry'
import type { State } from '../store/store'

const GAP = 10 // between the bar and the selection
const EDGE = 8 // kept clear of the view's edges

type Box = { left: number; top: number; right: number; bottom: number }

/** Where the bar goes, in window coordinates: centred over the selection,
 *  above it (clear of `above`), else below it, else at the top of the view;
 *  never past the view's sides. Null when the selection is scrolled out of
 *  the view. `board` is the board's top-left on screen, `sel` the selection
 *  in pasteboard points. */
export function barPlace(view: Box, board: { left: number; top: number }, sel: Rect, zoom: number,
  bar: { w: number; h: number }, above = 0): { left: number; top: number } | null {
  const top = board.top + sel.y * zoom, bottom = board.top + (sel.y + sel.h) * zoom
  const l = board.left + sel.x * zoom, r = board.left + (sel.x + sel.w) * zoom
  if (bottom < view.top || top > view.bottom || r < view.left || l > view.right) return null
  const mid = (l + r) / 2
  const left = Math.max(view.left + EDGE, Math.min(view.right - bar.w - EDGE, mid - bar.w / 2))
  const fits = (y: number) => y >= view.top + EDGE && y + bar.h <= view.bottom - EDGE
  const over = top - GAP - above - bar.h, under = bottom + GAP
  return { left, top: fits(over) ? over : fits(under) ? under : view.top + EDGE }
}

/** Whether the bar shows: something selected, nothing in front of the pages,
 *  and no drawing tool or drag in hand. */
export function barShown(s: State): boolean {
  return s.selection.length > 0 && s.doc.items.some((i) => s.selection.includes(i.id)) && !s.dialog && !s.guide && !s.gesture
    && !s.threading && (s.tool === 'select' || s.tool === 'text' || !!s.editing)
}
