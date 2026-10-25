// Where things are on the pasteboard, in points: spreads stacked down the
// pasteboard, each page's origin, an item's corners (turned about its
// centre), what is under a point, and what a moving edge snaps to.

import { onSubject } from '../compose/wrap'
import { isPartner } from '../model/subject'
import { pageSide, spreads as spreadsOf } from '../model/doc'
import type { Doc, Item } from '../model/types'

export const PASTE = 96 // pasteboard around the spreads
export const GAP = 48 // between spreads

export type Pt = { x: number; y: number }
export type Rect = { x: number; y: number; w: number; h: number }
export type SpreadBox = { index: number; pages: number[]; x: number; y: number; w: number; h: number }
export type Layout = { spreads: SpreadBox[]; origin: Pt[]; width: number; height: number }

/** Where the board's top-left sits in the scroller's scrolled content, past
 *  the slack (half the view each side) that lets any page reach the middle. */
export function boardOffset(sc: HTMLElement): Pt {
  const b = sc.querySelector<HTMLElement>('[data-studio-board]')
  if (!b) return { x: 0, y: 0 }
  const r = b.getBoundingClientRect(), s = sc.getBoundingClientRect()
  return { x: r.left - s.left + sc.scrollLeft, y: r.top - s.top + sc.scrollTop }
}

/** Spreads centred down the pasteboard; `origin[i]` is page i's top-left. */
export function layout(doc: Doc): Layout {
  const { w: pw, h: ph } = doc.size
  const groups = spreadsOf(doc)
  const widest = Math.max(pw * 2, ...groups.map((g) => g.length * pw))
  const origin: Pt[] = []
  let y = PASTE
  const spreads = groups.map((pages, index) => {
    const w = pages.length * pw
    // A lone right-hand page sits where it would in a pair.
    const lone = doc.facing && pages.length === 1 && pageSide(doc, pages[0]) === 'right' ? pw / 2 : 0
    const x = PASTE + (widest - w) / 2 + lone
    pages.forEach((p, k) => (origin[p] = { x: x + k * pw, y }))
    const box = { index, pages, x, y, w, h: ph }
    y += ph + GAP
    return box
  })
  return { spreads, origin, width: widest + 2 * PASTE, height: y - GAP + PASTE }
}

const rad = (deg: number) => (deg * Math.PI) / 180

/** A point turned by `deg` about `c`. */
export function turn(p: Pt, c: Pt, deg: number): Pt {
  if (!deg) return p
  const a = rad(deg), cos = Math.cos(a), sin = Math.sin(a)
  const dx = p.x - c.x, dy = p.y - c.y
  return { x: c.x + dx * cos - dy * sin, y: c.y + dx * sin + dy * cos }
}

/** An item's box on the pasteboard (unturned). */
export function itemBox(item: Item, origin: Pt): Rect {
  return { x: origin.x + item.x, y: origin.y + item.y, w: item.w, h: item.h }
}

export const centre = (r: Rect): Pt => ({ x: r.x + r.w / 2, y: r.y + r.h / 2 })

/** The four corners of an item, turned. */
export function corners(item: Item, origin: Pt): Pt[] {
  const b = itemBox(item, origin)
  const c = centre(b)
  return [{ x: b.x, y: b.y }, { x: b.x + b.w, y: b.y }, { x: b.x + b.w, y: b.y + b.h }, { x: b.x, y: b.y + b.h }]
    .map((p) => turn(p, c, item.rot))
}

/** The axis-aligned box around items (turned corners included). */
export function bounds(items: Item[], origins: (item: Item) => Pt): Rect | null {
  if (!items.length) return null
  const pts = items.flatMap((i) => corners(i, origins(i)))
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y)
  const x = Math.min(...xs), y = Math.min(...ys)
  return { x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y }
}

/** Whether `p` is on the item (inside its turned box, `slop` pt around it). */
export function hits(item: Item, origin: Pt, p: Pt, slop = 0): boolean {
  const b = itemBox(item, origin)
  const q = turn(p, centre(b), -item.rot)
  const pad = item.kind === 'line' ? Math.max(slop, 4) : slop
  return q.x >= b.x - pad && q.x <= b.x + b.w + pad && q.y >= b.y - pad && q.y <= b.y + b.h + pad
}

/** The topmost visible item under `p`. */
export function hitItem(doc: Doc, lay: Layout, p: Pt, slop = 0, held?: ReadonlySet<string>): Item | null {
  const pageIdx = new Map(doc.pages.map((pg, i) => [pg.id, i]))
  for (let k = doc.items.length - 1; k >= 0; k--) {
    const item = doc.items[k]
    if (item.hidden) continue
    const o = lay.origin[pageIdx.get(item.page) ?? -1]
    // The subject in front (model/subject.ts) is clicked only on the subject:
    // the lettering under the rest of its frame stays in reach. A selected
    // one is held whole, so it can be moved and resized.
    if (o && hits(item, o, p, slop) && (!isPartner(item, doc.items) || held?.has(item.id)
      || onSubject(item, p.x - o.x - item.x, p.y - o.y - item.y))) return item
  }
  return null
}

/** The page under `p` (or the nearest page of the spread it is beside). */
export function pageAt(doc: Doc, lay: Layout, p: Pt): number {
  let best = 0, bd = Infinity
  lay.origin.forEach((o, i) => {
    const dx = p.x < o.x ? o.x - p.x : p.x > o.x + doc.size.w ? p.x - o.x - doc.size.w : 0
    const dy = p.y < o.y ? o.y - p.y : p.y > o.y + doc.size.h ? p.y - o.y - doc.size.h : 0
    const d = dx * dx + dy * dy
    if (d < bd) { bd = d; best = i }
  })
  return best
}

// ── snapping ─────────────────────────────────────────────────────────────────

export type Snap = { x: number[]; y: number[] }

/** What an edge can snap to on a page, in pasteboard pt: its edges and
 *  centre, margins, columns, guides, and other items' edges and centres. */
export function snapTargets(doc: Doc, lay: Layout, page: number, skip: Set<string>): Snap {
  const o = lay.origin[page]
  const { w, h } = doc.size
  const m = doc.margins
  const left = pageSide(doc, page) === 'left'
  const ml = left ? m.o : m.i, mr = left ? m.i : m.o
  const x = [0, w / 2, w, ml, w - mr], y = [0, h / 2, h, m.t, h - m.b]
  const cw = (w - ml - mr - doc.cols.g * (doc.cols.n - 1)) / doc.cols.n
  for (let c = 1; c < doc.cols.n; c++) {
    x.push(ml + c * cw + (c - 1) * doc.cols.g, ml + c * (cw + doc.cols.g))
  }
  const pid = doc.pages[page].id
  for (const g of doc.guides) if (g.page === pid) (g.axis === 'v' ? x : y).push(g.at)
  for (const i of doc.items) {
    if (i.page !== pid || skip.has(i.id) || i.hidden || i.rot) continue
    x.push(i.x, i.x + i.w / 2, i.x + i.w)
    y.push(i.y, i.y + i.h / 2, i.y + i.h)
  }
  return { x: x.map((v) => v + o.x), y: y.map((v) => v + o.y) }
}

/** The smallest move (within `tol`) that puts one of `edges` on a target,
 *  and the target it lands on. */
export function snap1(edges: number[], targets: number[], tol: number): { d: number; at: number | null } {
  let best = { d: 0, at: null as number | null }, bd = tol
  for (const e of edges) for (const t of targets) {
    const d = t - e
    if (Math.abs(d) <= bd) { bd = Math.abs(d); best = { d, at: t } }
  }
  return best
}
