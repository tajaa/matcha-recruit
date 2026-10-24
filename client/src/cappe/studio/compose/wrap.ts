// Text wrap: what a text frame's lines keep away from. A frame, shape or
// graphic with `wrap` on the same page pushes text off its box (plus `o` pt);
// a picture with a cut-out `shape` can push it off the subject instead, row by
// row, wherever its crop puts the subject in the frame. The composer sets each
// line in the widest room left at its height (compose.ts `room`).
//
// Frames and wrapped items turned by any angle are left out: their boxes are
// what the rows are measured against.

import type { Doc, ImageItem, Item, Shape, TextItem } from '../model/types'

/** A rectangle in a text frame's own coordinates (from its top-left). */
export type Rect4 = { x0: number; y0: number; x1: number; y1: number }
/** By frame index: what that frame's text keeps away from. */
export type Wraps = Rect4[][]

const ROWS = 48

/** Where a frame shows its picture (render/layoutRender.ts imageHtml: object
 *  fit, object-position fx% fy%, scaled zoom% about that point), in the
 *  frame's coordinates, for a picture of aspect `ar` (width / height). */
export function picturePlace(item: Pick<ImageItem, 'w' | 'h' | 'fit' | 'fx' | 'fy' | 'zoom'>, ar: number): { x: number; y: number; w: number; h: number } {
  const z = item.zoom / 100
  let w0: number, h0: number
  if (item.fit === 'stretch') { w0 = item.w; h0 = item.h } else {
    const cover = item.fit === 'fill'
    w0 = cover ? Math.max(item.w, item.h * ar) : Math.min(item.w, item.h * ar)
    h0 = w0 / ar
  }
  const w = w0 * z, h = h0 * z
  return { x: (item.fx / 100) * (item.w - w) + 0, y: (item.fy / 100) * (item.h - h) + 0, w, h }
}

/** The subject's rows in the frame's own coordinates, clipped to the frame
 *  (what it shows), rows with nothing in them left out. */
export function subjectRows(item: ImageItem & { shape: Shape }): Rect4[] {
  const place = picturePlace(item, item.shape.ar)
  const n = item.shape.rows.length
  const out: Rect4[] = []
  item.shape.rows.forEach(([l, r], k) => {
    if (l > r) return
    const y0 = Math.max(0, place.y + (k / n) * place.h), y1 = Math.min(item.h, place.y + ((k + 1) / n) * place.h)
    const x0 = Math.max(0, place.x + l * place.w), x1 = Math.min(item.w, place.x + r * place.w)
    if (y1 > y0 && x1 > x0) out.push({ x0, y0, x1, y1 })
  })
  return out
}

/** Whether a point in a frame's own coordinates is on its subject (a cut-out
 *  partner is clicked only there). */
export function onSubject(item: ImageItem, x: number, y: number): boolean {
  if (!item.shape) return true
  return subjectRows(item as ImageItem & { shape: Shape }).some((r) => x >= r.x0 && x <= r.x1 && y >= r.y0 && y <= r.y1)
}

/** What `item` pushes text off, on its page. */
function obstacles(item: Item): Rect4[] {
  if (!('wrap' in item) || !item.wrap) return []
  const o = item.wrap.o
  if (item.kind === 'image' && item.wrap.m === 'subject' && item.shape) {
    return subjectRows(item as ImageItem & { shape: Shape })
      .map((r) => ({ x0: item.x + r.x0 - o, y0: item.y + r.y0 - o, x1: item.x + r.x1 + o, y1: item.y + r.y1 + o }))
  }
  return [{ x0: item.x - o, y0: item.y - o, x1: item.x + item.w + o, y1: item.y + item.h + o }]
}

/** What each of a thread's frames keeps away from, and a key that changes
 *  whenever that does (the composer's cache holds it). */
export function threadWraps(doc: Doc, frames: TextItem[]): { wraps: Wraps | undefined; key: string } {
  const wrapping = doc.items.filter((i) => i.kind !== 'text' && i.kind !== 'line' && !i.hidden && !i.rot && 'wrap' in i && i.wrap)
  if (!wrapping.length) return { wraps: undefined, key: '' }
  let any = false
  const wraps = frames.map((f) => {
    if (f.rot) return []
    const mine = wrapping.filter((i) => i.page === f.page && i.id !== f.id).flatMap(obstacles)
      .filter((r) => r.x0 < f.x + f.w && r.x1 > f.x && r.y0 < f.y + f.h && r.y1 > f.y)
      .map((r) => ({ x0: r.x0 - f.x, y0: r.y0 - f.y, x1: r.x1 - f.x, y1: r.y1 - f.y }))
    if (mine.length) any = true
    return mine
  })
  if (!any) return { wraps: undefined, key: '' }
  return { wraps, key: wraps.map((list) => list.map((r) => `${r.x0.toFixed(2)},${r.y0.toFixed(2)},${r.x1.toFixed(2)},${r.y1.toFixed(2)}`).join(';')).join('|') }
}

/** A cut-out's subject from its pixels (RGBA, top row first): for each of
 *  `rows` bands, the leftmost and rightmost columns with any pixel at least
 *  half opaque, as fractions of the width. */
export function shapeFromAlpha(data: Uint8ClampedArray, w: number, h: number, rows = ROWS): Shape {
  const n = Math.max(1, Math.min(rows, h))
  const out: [number, number][] = []
  for (let k = 0; k < n; k++) {
    const y0 = Math.floor((k * h) / n), y1 = Math.max(y0 + 1, Math.floor(((k + 1) * h) / n))
    let lo = w, hi = -1
    for (let y = y0; y < y1; y++) {
      const row = y * w * 4
      for (let x = 0; x < lo; x++) if (data[row + x * 4 + 3] >= 128) { lo = x; break }
      for (let x = w - 1; x > hi; x--) if (data[row + x * 4 + 3] >= 128) { hi = x; break }
    }
    const r3 = (v: number) => Math.round(v * 1000) / 1000
    out.push(hi < lo ? [1, 0] : [r3(lo / w), r3((hi + 1) / w)])
  }
  return { ar: Math.round((w / h) * 10000) / 10000, rows: out }
}
