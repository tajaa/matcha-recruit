// Using a template (templates.ts): its frames fitted to the story's page
// size, anything touching a page edge carried out to the bleed, type scaled
// with the page, and each run of linked frames made one thread. A blank page
// (nothing on it but empty text frames) takes the template; otherwise it
// goes on a new page after the one in view, so nothing is ever covered or
// lost. One undo step.

import { allIds, newId, newItem } from '../../model/doc'
import { CHAR_DEFAULTS, round } from '../../model/limits'
import { addPages, deleteItems } from '../../model/ops'
import type { Doc, Item, Para, Thread } from '../../model/types'
import type { StudioCtx } from '../context'
import { BASE, type Template, type TItem } from './templates'

const PREFIX: Record<TItem['kind'], string> = { text: 't', image: 'i', rect: 'r', ellipse: 'e', line: 'l', graphic: 'g' }

/** The template's items and threads on page `pageId` of `doc`, with ids
 *  `doc` doesn't use. */
export function templateItems(t: Template, doc: Doc, pageId: string): { items: Item[]; threads: Thread[] } {
  const sx = doc.size.w / BASE.w, sy = doc.size.h / BASE.h, sf = Math.min(sx, sy)
  const b = doc.bleed
  const taken = allIds(doc)
  const fresh = (prefix: string) => { const id = newId(prefix, taken); taken.push(id); return id }
  const items: Item[] = []
  const threads = new Map<string, Thread>()
  t.items.forEach((ti, k) => {
    let x = ti.x * sx, y = ti.y * sy, w = ti.w * sx, h = ti.h * sy
    if (ti.kind !== 'text') {
      // Edge to edge means out to the bleed.
      if (ti.x <= 0) { x -= b; w += b }
      if (ti.y <= 0) { y -= b; h += b }
      if (ti.x + ti.w >= BASE.w) w += b
      if (ti.y + ti.h >= BASE.h) h += b
    }
    const id = fresh(PREFIX[ti.kind])
    const base = newItem(ti.kind, pageId, id, { x, y, w, h })
    const common = { rot: ti.rot ?? 0, opacity: ti.opacity ?? 100, name: ti.name ?? '' }
    switch (ti.kind) {
      case 'text': {
        items.push({ ...base, ...common, kind: 'text', cols: ti.cols ?? 1, gutter: round((ti.gutter ?? 12) * sx),
          inset: round((ti.inset ?? 0) * sf), valign: ti.valign ?? 'top', fill: ti.fill ?? null, stroke: null } as Item)
        const key = ti.thread ?? `own:${k}`
        const thread = threads.get(key)
        if (thread) thread.frames.push(id)
        else threads.set(key, { id: fresh('s'), frames: [id], paras: [] })
        if (ti.parts) {
          threads.get(key)!.paras.push(...ti.parts.map((p): Para => {
            const para: Para = { ...p.para, runs: [{ ...p.char, size: round((p.char.size ?? CHAR_DEFAULTS.size) * sf), t: p.text }] }
            for (const f of ['lead', 'sb', 'sa', 'li', 'ri', 'fi'] as const) if (para[f]) para[f] = round(para[f]! * sf)
            return para
          }))
        }
        break
      }
      case 'image':
        items.push({ ...base, ...common, kind: 'image', fill: ti.fill ?? null, radius: round((ti.radius ?? 0) * sf) } as Item)
        break
      case 'rect':
        items.push({ ...base, ...common, kind: 'rect', fill: ti.fill, radius: round((ti.radius ?? 0) * sf),
          stroke: ti.stroke ? { c: ti.stroke.c, w: round(ti.stroke.w * sf) } : null } as Item)
        break
      case 'ellipse':
        items.push({ ...base, ...common, kind: 'ellipse', fill: ti.fill } as Item)
        break
      case 'line':
        items.push({ ...base, ...common, kind: 'line', stroke: { c: ti.stroke.c, w: round(ti.stroke.w * sf) } } as Item)
        break
      case 'graphic':
        items.push({ ...base, ...common, kind: 'graphic', src: ti.src, color: ti.color, fit: ti.fit } as Item)
        break
    }
  })
  return { items, threads: [...threads.values()].map((th) => (th.paras.length ? th : { ...th, paras: [{ runs: [{ t: '' }] }] })) }
}

/** The faces a template sets: [family, weight, italic]. */
export function templateFaces(t: Template): [string, number, boolean][] {
  const seen = new Map<string, [string, number, boolean]>()
  for (const ti of t.items) {
    if (ti.kind !== 'text') continue
    for (const p of ti.parts ?? []) {
      const f: [string, number, boolean] = [p.char.font ?? CHAR_DEFAULTS.font, p.char.wt ?? CHAR_DEFAULTS.wt, !!p.char.it]
      seen.set(f.join('|'), f)
    }
  }
  return [...seen.values()]
}

/** Whether page `index` has nothing on it but empty, unlocked text frames. */
export function blankPage(doc: Doc, index: number): boolean {
  const id = doc.pages[index]?.id
  return doc.items.filter((i) => i.page === id).every((i) => {
    if (i.kind !== 'text' || i.locked) return false
    const t = doc.threads.find((th) => th.frames.includes(i.id))
    return !t || t.paras.every((p) => p.runs.every((r) => !r.t))
  })
}

/** A one-page document of the template, for its thumbnail. */
export function previewDoc(t: Template, doc: Doc): Doc {
  const base: Doc = { ...doc, pages: [{ id: 'p1' }], items: [], threads: [], guides: [], paywall_page: null }
  return { ...base, ...templateItems(t, base, 'p1') }
}

/** Use a template: on the page in view if it's blank, else a new page after
 *  it. Returns the page it went on. */
export async function applyTemplate(c: StudioCtx, t: Template): Promise<number> {
  const book = c.fonts.book
  await Promise.all(templateFaces(t).map(([f, w, i]) => book.face(f, w, i)).filter((f) => !!f)
    .map((f) => c.fonts.ensure(f!).catch(() => {})))
  const s = c.store.get()
  const page = s.page
  const blank = blankPage(s.doc, page)
  const target = blank ? page : page + 1
  c.editor.close()
  c.store.edit((d) => {
    const onPage = d.items.filter((i) => i.page === d.pages[page].id).map((i) => i.id)
    const next = blank ? deleteItems(d, onPage) : addPages(d, page)
    const built = templateItems(t, next, next.pages[target].id)
    return { ...next, items: [...next.items, ...built.items], threads: [...next.threads, ...built.threads] }
  }, { key: `template:${Date.now()}`, extra: { page: target, selection: [], tool: 'select', threading: null } })
  c.store.seal()
  c.fit?.(target, false)
  return target
}
