// Putting what the side panel offers on a page: where a click (the middle of
// the page in view) or a drop (the page and point under it) lands, and how
// each kind goes there. Each addition is one undo step and ends selected,
// with the Selection tool in hand.

import { layout, hitItem, pageAt } from '../../canvas/geometry'
import { allIds, newId, pageSide } from '../../model/doc'
import { CHAR_DEFAULTS, clamp } from '../../model/limits'
import { addItem, arrange, patchItems } from '../../model/ops'
import type { GraphicCard } from '../../model/graphics'
import type { Doc, Item, Para } from '../../model/types'
import { toAsset } from '../../api'
import type { CappeAsset } from '../../../types'
import type { StudioCtx } from '../context'
import { facesOf, type Box, type ElementSpec, type TextStyle } from './catalog'

/** Where something lands: a page (its index then, and its id: a text style's
 *  faces or an archive picture take a moment, and pages can move or go
 *  meanwhile), a point on it (page points), and what was under it when dropped. */
export type At = { page: number; pageId: string; x: number; y: number; hit: Item | null; dropped: boolean }

/** Where a drop at (clientX, clientY) lands; with none, the middle of the
 *  page in view. */
export function landing(c: StudioCtx, drop?: { clientX: number; clientY: number }): At {
  const s = c.store.get()
  const board = drop ? c.board() : null
  const id = (page: number) => s.doc.pages[page]?.id ?? ''
  if (!drop || !board) return { page: s.page, pageId: id(s.page), x: s.doc.size.w / 2, y: s.doc.size.h / 2, hit: null, dropped: false }
  const r = board.getBoundingClientRect()
  const zoom = s.view.zoom
  const p = { x: (drop.clientX - r.left) / zoom, y: (drop.clientY - r.top) / zoom }
  const lay = layout(s.doc)
  const page = pageAt(s.doc, lay, p)
  const o = lay.origin[page]
  return { page, pageId: id(page), x: p.x - o.x, y: p.y - o.y, hit: hitItem(s.doc, lay, p), dropped: true }
}

/** Where `at`'s page is now; it may have moved, or gone, while what lands on
 *  it was on its way. */
function pageNow(doc: Doc, at: At): number {
  const i = doc.pages.findIndex((p) => p.id === at.pageId)
  if (i < 0) throw new Error('The page it was going on isn’t there any more.')
  return i
}

/** The page's text area: inside its margins (its inside margin on the spine side). */
function textArea(doc: Doc, page = 0) {
  const left = pageSide(doc, page) === 'left' ? doc.margins.o : doc.margins.i
  return { x: left, w: doc.size.w - doc.margins.i - doc.margins.o, h: doc.size.h - doc.margins.t - doc.margins.b }
}

/** A box of `size` centred on the landing point, kept on the page (to its bleed). */
function centred(doc: Doc, at: At, size: Box) {
  const b = doc.bleed
  const fit = (v: number, len: number, page: number) => (len >= page + 2 * b ? -b : clamp(v - len / 2, -b, page + b - len))
  return { x: fit(at.x, size.w, doc.size.w), y: fit(at.y, size.h, doc.size.h), w: size.w, h: size.h }
}

function placed(doc: Doc, el: ElementSpec, at: At) {
  const { w, h } = doc.size
  const b = doc.bleed
  switch (el.place) {
    case 'page': return { x: -b, y: -b, w: w + 2 * b, h: h + 2 * b }
    case 'top': return { x: -b, y: -b, w: w + 2 * b, h: h * 0.2 + b }
    case 'bottom': return { x: -b, y: h * 0.8, w: w + 2 * b, h: h * 0.2 + b }
    case 'side': return { x: -b, y: -b, w: w / 3 + b, h: h + 2 * b }
    default: return centred(doc, at, el.size(doc))
  }
}

function select(c: StudioCtx, id: string, page: number): void {
  c.editor.close()
  c.store.set({ selection: [id], tool: 'select', page, threading: null })
}

/** A shape, line, frame or colour block. Returns its id. */
export function addElement(c: StudioCtx, el: ElementSpec, at: At = landing(c)): string {
  let id = ''
  c.store.edit((d) => {
    const r = addItem(d, el.kind, d.pages[at.page].id, placed(d, el, at))
    id = r.id
    let next = el.patch ? patchItems(r.doc, [id], el.patch) : r.doc
    if (el.back) next = arrange(next, [id], 'back')
    return next
  }, { key: `add:${Date.now()}` })
  select(c, id, at.page)
  return id
}

function paras(style: TextStyle): Para[] {
  return style.parts.map((p) => ({ ...p.para, runs: [{ ...p.char, t: p.text }] }))
}

/** A text style or pairing, in a frame sized to its words. Its faces load
 *  first, so it is measured in them. Returns the frame's id. */
export async function addText(c: StudioCtx, style: TextStyle, at: At = landing(c)): Promise<string> {
  const book = c.fonts.book
  const faces = facesOf(style, CHAR_DEFAULTS).map(([f, w, i]) => book.face(f, w, i)).filter((f) => !!f)
  await Promise.all(faces.map((f) => c.fonts.ensure(f!).catch(() => {})))
  const doc = c.store.get().doc
  const page = pageNow(doc, at)
  const area = textArea(doc, page)
  const w = style.width === 'content' ? area.w : style.width === 'half' ? Math.min(area.w, Math.max(area.w / 2, 216)) : Math.min(area.w, 180)
  // Clicked in, a frame as wide as the text area lines up with its margins.
  const place = (box: { x: number; y: number; w: number; h: number }) =>
    (!at.dropped && w === area.w ? { ...box, x: area.x } : box)
  const key = `add:${Date.now()}`
  let id = ''
  c.store.edit((d) => {
    const r = addItem(d, 'text', at.pageId, place(centred(d, at, { w, h: area.h })))
    id = r.id
    const thread = newId('s', allIds(r.doc))
    return { ...r.doc, threads: [...r.doc.threads, { id: thread, frames: [id], paras: paras(style) }] }
  }, { key })
  // Down to its last line, then centred on where it landed.
  const s = c.store.get()
  const thread = s.doc.threads.find((t) => t.frames.includes(id))
  const lines = thread?.comp?.lines ?? []
  if (lines.length && thread && !s.overset.has(thread.id)) {
    const last = lines[lines.length - 1]
    const size = thread.paras[last[1]]?.runs[0]?.size ?? CHAR_DEFAULTS.size
    const h = Math.ceil(last[5] + size * 0.3 + 2)
    const box = place(centred(s.doc, at, { w, h }))
    c.store.edit((d) => patchItems(d, [id], { x: box.x, y: box.y, h }), { key })
  }
  c.store.seal()
  select(c, id, page)
  return id
}

/** A library picture: into the empty frame it was dropped on (or the empty
 *  frame selected, for a click), else a new frame its shape. Returns the
 *  frame's id. */
export function addPicture(c: StudioCtx, asset: CappeAsset, at: At = landing(c)): string {
  c.store.set((x) => ({ assets: { ...x.assets, [asset.id]: toAsset(asset) } }))
  const s = c.store.get()
  // An archive picture arrives a moment after its drop: go by what is there now.
  const find = (id?: string) => (id ? s.doc.items.find((i) => i.id === id) : undefined)
  const hit = find(at.hit?.id)
  const chosen = s.selection.length === 1 ? find(s.selection[0]) : undefined
  const target = at.dropped
    ? (hit?.kind === 'image' && !hit.locked ? hit : null)
    : (chosen?.kind === 'image' && !chosen.asset_id ? chosen : null)
  if (target) {
    c.store.edit((d) => patchItems(d, [target.id], { asset_id: asset.id }), { key: `add:${Date.now()}` })
    const page = s.doc.pages.findIndex((p) => p.id === target.page)
    select(c, target.id, page)
    return target.id
  }
  const ratio = asset.width && asset.height ? asset.width / asset.height : 1.5
  const area = textArea(s.doc)
  let w = Math.min(area.w, s.doc.size.w * 0.6)
  let h = w / ratio
  if (h > s.doc.size.h * 0.6) { h = s.doc.size.h * 0.6; w = h * ratio }
  let id = ''
  const page = pageNow(s.doc, at)
  c.store.edit((d) => {
    const r = addItem(d, 'image', at.pageId, centred(d, at, { w, h }))
    id = r.id
    return patchItems(r.doc, [id], { asset_id: asset.id })
  }, { key: `add:${Date.now()}` })
  select(c, id, page)
  return id
}

/** How big a graphic starts, and in what colour, by its group. */
const GRAPHIC_START: Record<GraphicCard['group'], { size: number; color: string }> = {
  shapes: { size: 144, color: '#d9d4cc' }, badges: { size: 144, color: '#b4532a' }, icons: { size: 72, color: '#1a1a1a' },
  stickers: { size: 120, color: '#1a1a1a' }, lines: { size: 216, color: '#1a1a1a' }, patterns: { size: 0, color: '#d9d4cc' },
}

/** One of the bank's graphics, its own shape (a pattern covers the page,
 *  behind everything). Returns its id. */
export function addGraphic(c: StudioCtx, g: GraphicCard, at: At = landing(c)): string {
  const start = GRAPHIC_START[g.group]
  const doc = c.store.get().doc
  const ratio = g.w > 0 && g.h > 0 ? g.w / g.h : 1
  const longest = start.size
  const size = ratio >= 1 ? { w: longest, h: longest / ratio } : { w: longest * ratio, h: longest }
  const b = doc.bleed
  const box = g.group === 'patterns' ? { x: -b, y: -b, w: doc.size.w + 2 * b, h: doc.size.h + 2 * b } : centred(doc, at, size)
  let id = ''
  c.store.edit((d) => {
    const r = addItem(d, 'graphic', d.pages[at.page].id, box)
    id = r.id
    const next = patchItems(r.doc, [id], { src: g.sha, color: g.mono ? start.color : null, fit: g.fit, name: g.name.slice(0, 60) })
    return g.group === 'patterns' ? arrange(next, [id], 'back') : next
  }, { key: `add:${Date.now()}` })
  select(c, id, at.page)
  return id
}
