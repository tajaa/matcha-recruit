// Resizing and turning an item by its handles, as pure functions of where the
// drag started and where the pointer is now (pasteboard points).

import { round } from '../model/limits'
import type { Item } from '../model/types'
import { turn, type Pt } from './geometry'

/** The eight handles: which way each moves the edges (−1 left/top, 1 right/bottom). */
export const HANDLES: Record<string, [number, number]> = {
  nw: [-1, -1], n: [0, -1], ne: [1, -1], e: [1, 0], se: [1, 1], s: [0, 1], sw: [-1, 1], w: [-1, 0],
}

type Geo = Pick<Item, 'x' | 'y' | 'w' | 'h' | 'rot'>

/** An item resized by dragging handle `h` by (dx, dy): the opposite handle
 *  stays put, whatever the item's turn. `keep`: keep its proportions;
 *  `fromCentre`: grow from the middle (Alt). */
export function resize(start: Geo, h: string, dx: number, dy: number,
  { keep = false, fromCentre = false, min = 1 }: { keep?: boolean; fromCentre?: boolean; min?: number } = {}): Geo {
  const [hx, hy] = HANDLES[h]
  const local = turn({ x: dx, y: dy }, { x: 0, y: 0 }, -start.rot)
  const k = fromCentre ? 2 : 1
  let w = Math.max(min, start.w + hx * local.x * k)
  let hgt = Math.max(min, start.h + hy * local.y * k)
  if (keep && start.w > 0 && start.h > 0) {
    const ratio = start.w / start.h
    if (hx && hy) {
      if (w / ratio > hgt) hgt = w / ratio
      else w = hgt * ratio
    } else if (hx) hgt = w / ratio
    else w = hgt * ratio
  }
  const c0 = { x: start.x + start.w / 2, y: start.y + start.h / 2 }
  let c1: Pt
  if (fromCentre) c1 = c0
  else {
    // The anchor (opposite handle) stays where it is on the page.
    const anchor = turn({ x: c0.x - (hx * start.w) / 2, y: c0.y - (hy * start.h) / 2 }, c0, start.rot)
    const back = turn({ x: (-hx * w) / 2, y: (-hy * hgt) / 2 }, { x: 0, y: 0 }, start.rot)
    c1 = { x: anchor.x - back.x, y: anchor.y - back.y }
  }
  return { x: round(c1.x - w / 2), y: round(c1.y - hgt / 2), w: round(w), h: round(hgt), rot: start.rot }
}

/** The turn after dragging the rotation handle from `p0` to `p` around `c`
 *  (Shift: in steps of 15°), between −180 and 180. */
export function rotate(start: number, c: Pt, p0: Pt, p: Pt, step = false): number {
  const a0 = Math.atan2(p0.y - c.y, p0.x - c.x)
  const a1 = Math.atan2(p.y - c.y, p.x - c.x)
  let deg = start + ((a1 - a0) * 180) / Math.PI
  if (step) deg = Math.round(deg / 15) * 15
  deg = ((((deg + 180) % 360) + 360) % 360) - 180
  return round(deg)
}

/** A box dragged out from `a` to `b` (Shift: square, or a line at 45°). */
export function dragBox(a: Pt, b: Pt, { square = false, line = false } = {}): { x: number; y: number; w: number; h: number; flip: boolean } {
  let dx = b.x - a.x, dy = b.y - a.y
  if (square) {
    if (line) {
      const ang = Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4)
      const len = Math.hypot(dx, dy)
      dx = Math.cos(ang) * len
      dy = Math.sin(ang) * len
    } else {
      const s = Math.max(Math.abs(dx), Math.abs(dy))
      dx = Math.sign(dx || 1) * s
      dy = Math.sign(dy || 1) * s
    }
  }
  const x = Math.min(a.x, a.x + dx), y = Math.min(a.y, a.y + dy)
  // A line from bottom-left to top-right is flipped.
  return { x: round(x), y: round(y), w: round(Math.abs(dx)), h: round(Math.abs(dy)), flip: dx * dy < 0 }
}
