import { allIds, newId } from '../../model/doc'
import { CHAR_DEFAULTS, LIMITS, docProblem, round } from '../../model/limits'
import { portableCollection } from '../../model/collections'
import type { Doc, Item } from '../../model/types'
import type { StudioCtx } from '../context'
import { blankPage } from './applyTemplate'
import { layoutPreparation } from './preparation'

/** Rebase a collection's ids, fit it to this document, and keep every text
 *  thread linked. A fully blank story takes it; otherwise insert after the
 *  current spread. A spacer keeps the cover on the right on facing pages. */
export function insertCollection(doc: Doc, source: Doc, pageId: string): { doc: Doc; page: number; spacer: boolean } {
  const at = doc.pages.findIndex((p) => p.id === pageId)
  if (at < 0) throw new Error('The page that collection was for has been deleted.')
  const empty = !doc.guides.length && doc.pages.every((_, k) => blankPage(doc, k))
  const after = doc.facing && at % 2 === 1 && at + 1 < doc.pages.length ? at + 2 : at + 1
  const spacer = !empty && doc.facing && source.facing && after % 2 === 1
  const target = empty ? 0 : after + Number(spacer)
  const base: Doc = empty ? { ...doc, margins: source.margins, cols: source.cols, baseline: source.baseline,
    grid: source.grid, facing: source.facing, paper: source.paper, pages: [], items: [], threads: [], guides: [] } : doc
  const used = allIds(doc)
  const fresh = (prefix: string) => { const id = newId(prefix, used); used.push(id); return id }
  const pages = source.pages.map(() => ({ id: fresh('p') }))
  const pageIds = new Map(source.pages.map((p, k) => [p.id, pages[k].id]))
  const itemIds = new Map(source.items.map((i) => [i.id, fresh(i.kind[0])]))
  const sx = doc.size.w / source.size.w, sy = doc.size.h / source.size.h, sf = Math.min(sx, sy)
  const scale = (n: number) => round(n * sf)
  const portable = portableCollection(source)
  const items = portable.items.map((i): Item => {
    let x = i.x * sx, y = i.y * sy, w = i.w * sx, h = i.h * sy
    // Rebuild exact page/bleed edges; keep deliberate off-page positioning.
    if (i.kind !== 'text') {
      if (i.x === -source.bleed || i.x === 0) { x = -doc.bleed; w += i.x * sx - x }
      if (i.y === -source.bleed || i.y === 0) { y = -doc.bleed; h += i.y * sy - y }
      if (i.x + i.w === source.size.w + source.bleed || i.x + i.w === source.size.w) w = doc.size.w + doc.bleed - x
      if (i.y + i.h === source.size.h + source.bleed || i.y + i.h === source.size.h) h = doc.size.h + doc.bleed - y
    }
    let out: Item = { ...i, id: itemIds.get(i.id)!, page: pageIds.get(i.page)!, x: round(x), y: round(y), w: round(w), h: round(h) }
    if ('stroke' in out && out.stroke) out = { ...out, stroke: { ...out.stroke, w: scale(out.stroke.w) } }
    if ('radius' in out) out = { ...out, radius: scale(out.radius) }
    if (out.kind === 'text') out = { ...out, gutter: round(out.gutter * sx), inset: scale(out.inset) }
    if (out.kind === 'graphic') out = { ...out, tile: scale(out.tile) }
    return out
  })
  const threads = portable.threads.map((t) => ({ id: fresh('s'), frames: t.frames.map((f) => itemIds.get(f)!),
    paras: t.paras.map((p) => {
      const next = { ...p, runs: p.runs.map((r) => ({ ...r, size: scale(r.size ?? CHAR_DEFAULTS.size) })) }
      for (const key of ['li', 'ri', 'fi', 'sb', 'sa', 'lead'] as const) if (next[key]) next[key] = scale(next[key]!)
      return next
    }),
  }))
  const guides = portable.guides.map((g) => ({ ...g, id: fresh('g'), page: pageIds.get(g.page)!, at: round(g.at * (g.axis === 'v' ? sx : sy)) }))
  const added = spacer ? [{ id: fresh('p') }, ...pages] : pages
  const done: Doc = { ...base,
    pages: empty ? pages : [...base.pages.slice(0, after), ...added, ...base.pages.slice(after)],
    items: [...base.items, ...items], threads: [...base.threads, ...threads], guides: [...base.guides, ...guides],
    // Existing subscriber pages follow their original page after insertion.
    paywall_page: empty ? null : doc.paywall_page !== null && after < doc.paywall_page ? doc.paywall_page + added.length : doc.paywall_page,
  }
  if (empty) {
    done.margins = Object.fromEntries(Object.entries(source.margins).map(([k, n]) => [k, scale(n)])) as Doc['margins']
    done.cols = { n: source.cols.n, g: round(source.cols.g * sx) }
    done.baseline = { start: round(source.baseline.start * sy), step: scale(source.baseline.step) }
    done.grid = { step: scale(source.grid.step) }
  }
  if (done.guides.length > LIMITS.MAX_GUIDES) throw new Error(`The collection wasn’t added: A story holds at most ${LIMITS.MAX_GUIDES} guides.`)
  // The save schema clamps measurements. Refuse an extreme resize instead
  // of showing a layout that changes shape as soon as it is saved.
  const outside = items.some((i) => Math.abs(i.x) > LIMITS.COORD || Math.abs(i.y) > LIMITS.COORD
    || i.w > LIMITS.COORD || i.h > LIMITS.COORD || ('stroke' in i && i.stroke && i.stroke.w > LIMITS.STROKE_MAX)
    || ('radius' in i && i.radius > LIMITS.RADIUS_MAX)
    || (i.kind === 'text' && (i.gutter > LIMITS.GUTTER_MAX || i.inset > LIMITS.GUTTER_MAX))
    || (i.kind === 'graphic' && (i.tile < LIMITS.TILE_MIN || i.tile > LIMITS.TILE_MAX)))
    || threads.some((t) => t.paras.some((p) => (p.lead ?? 0) > LIMITS.LEAD_MAX
      || (['li', 'ri', 'fi', 'sb', 'sa'] as const).some((k) => (p[k] ?? 0) > LIMITS.INDENT_MAX)
      || p.runs.some((r) => r.size < 1 || r.size > LIMITS.SIZE_MAX)))
    || guides.some((g) => Math.abs(g.at) > LIMITS.COORD)
    || (empty && (done.baseline.step < 1 || done.baseline.step > 144 || done.grid.step < 1 || done.grid.step > 288))
  if (outside) throw new Error('The collection wasn’t added: Its measurements exceed the Studio’s limits at this page size. Use a page size closer to the collection’s original.')
  const problem = docProblem(done)
  if (problem) throw new Error(`The collection wasn’t added: ${problem}`)
  return { doc: done, page: target, spacer }
}

export async function applyCollection(c: StudioCtx, source: Doc): Promise<number | null> {
  if (layoutPreparation.has(c.store)) return null
  const clicked = c.store.get()
  const pageId = clicked.doc.pages[clicked.page]?.id
  if (!pageId) return null
  layoutPreparation.add(c.store)
  try {
    await c.fonts.ensureDoc(source)
    c.editor.close()
    const built = insertCollection(c.store.get().doc, source, pageId)
    c.store.edit(() => built.doc, { key: `collection:${Date.now()}`, extra: {
      page: built.page, selection: [], tool: 'select', threading: null,
      notice: built.spacer ? 'Collection added. A blank page keeps its cover on the right and its spreads facing.' : null,
    } })
    c.store.seal()
    c.fit?.(built.page, false)
    return built.page
  } finally {
    layoutPreparation.delete(c.store)
  }
}
