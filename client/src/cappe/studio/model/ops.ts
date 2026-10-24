// What the Studio does to a document, as pure functions: each returns a new
// document (or the same one when nothing changed). The canvas, the panels,
// the menus and the keys all go through these.

import { LIMITS, round } from './limits'
import { allIds, mergeRuns, newId, newItem, paraText, sparseChar, sparsePara } from './doc'
import type { CharAttrs, Doc, Guide, Item, Kind, Para, ParaAttrs, Thread } from './types'

type Box = { x: number; y: number; w: number; h: number }

const byId = (doc: Doc) => new Map(doc.items.map((i) => [i.id, i]))

// ── items ────────────────────────────────────────────────────────────────────

export function addItem(doc: Doc, kind: Kind, page: string, box: Box): { doc: Doc; id: string } {
  const id = newId(kind === 'text' ? 't' : kind === 'image' ? 'i' : kind[0], allIds(doc))
  return { doc: { ...doc, items: [...doc.items, newItem(kind, page, id, box)] }, id }
}

export function updateItems(doc: Doc, ids: Iterable<string>, fn: (item: Item) => Item): Doc {
  const want = new Set(ids)
  let changed = false
  const items = doc.items.map((i) => {
    if (!want.has(i.id)) return i
    const next = fn(i)
    if (next !== i) changed = true
    return next
  })
  return changed ? { ...doc, items } : doc
}

/** Set fields on items (numbers rounded as the server keeps them). */
export function patchItems(doc: Doc, ids: Iterable<string>, patch: Record<string, unknown>): Doc {
  const clean = Object.fromEntries(Object.entries(patch).map(([k, v]) => [k, typeof v === 'number' ? round(v) : v]))
  if (('fill' in patch || 'color' in patch) && !('fill_swatch' in patch)) clean.fill_swatch = undefined
  return updateItems(doc, ids, (i) => (Object.entries(clean).every(([k, v]) => (i as Record<string, unknown>)[k] === v)
    ? i : ({ ...i, ...clean } as Item)))
}

export function moveItems(doc: Doc, ids: Iterable<string>, dx: number, dy: number): Doc {
  if (!dx && !dy) return doc
  return updateItems(doc, ids, (i) => (i.locked ? i : { ...i, x: round(i.x + dx), y: round(i.y + dy) }))
}

/** Take items away; their frames leave their threads, and a thread left with
 *  no frame goes with its text. */
export function deleteItems(doc: Doc, ids: Iterable<string>): Doc {
  const gone = new Set([...ids].filter((id) => !byId(doc).get(id)?.locked))
  if (!gone.size) return doc
  const threads = doc.threads
    .map((t) => (t.frames.some((f) => gone.has(f)) ? { ...t, frames: t.frames.filter((f) => !gone.has(f)), comp: undefined } : t))
    .filter((t) => t.frames.length)
  return { ...doc, items: doc.items.filter((i) => !gone.has(i.id)), threads: threads.map(stripComp) }
}

function stripComp(t: Thread): Thread {
  if (t.comp !== undefined || !('comp' in t)) return t
  const rest = { ...t }
  delete rest.comp
  return rest
}

export type Arrange = 'front' | 'forward' | 'backward' | 'back'

export function arrange(doc: Doc, ids: Iterable<string>, how: Arrange): Doc {
  const want = new Set(ids)
  const items = [...doc.items]
  if (how === 'front') return { ...doc, items: [...items.filter((i) => !want.has(i.id)), ...items.filter((i) => want.has(i.id))] }
  if (how === 'back') return { ...doc, items: [...items.filter((i) => want.has(i.id)), ...items.filter((i) => !want.has(i.id))] }
  const order = how === 'forward' ? [...items.keys()].reverse() : [...items.keys()]
  for (const k of order) {
    const j = how === 'forward' ? k + 1 : k - 1
    if (want.has(items[k].id) && j >= 0 && j < items.length && !want.has(items[j].id)) [items[k], items[j]] = [items[j], items[k]]
  }
  return { ...doc, items }
}

/** Copies of items, offset; copied text frames take their text along when
 *  they hold all of their thread (linked frames copied together stay linked).
 *  Returns the copies' ids. */
export function duplicate(doc: Doc, ids: string[], dx = 12, dy = 12, page?: string): { doc: Doc; ids: string[] } {
  let next = doc
  const made: string[] = []
  const copies = new Map<string, string>()
  for (const id of ids) {
    const item = byId(next).get(id)
    if (!item || copies.has(id)) continue
    const copyId = newId(item.kind === 'text' ? 't' : item.kind[0], allIds(next))
    const copy = { ...item, id: copyId, page: page ?? item.page, x: round(item.x + dx), y: round(item.y + dy), locked: false } as Item
    next = { ...next, items: [...next.items, copy] }
    copies.set(id, copyId)
    made.push(copyId)
  }
  for (const thread of doc.threads) {
    if (!thread.frames.every((f) => copies.has(f))) continue
    const frames = thread.frames.map((f) => copies.get(f)!)
    next = { ...next, threads: [...next.threads, { id: newId('s', allIds(next)), frames, paras: thread.paras }] }
  }
  return { doc: next, ids: made }
}

// ── pages ────────────────────────────────────────────────────────────────────

export function addPages(doc: Doc, after: number, count = 1): Doc {
  const pages = [...doc.pages]
  const taken = allIds(doc)
  for (let k = 0; k < count && pages.length < LIMITS.MAX_PAGES; k++) {
    const id = newId('p', [...taken, ...pages.map((p) => p.id)])
    pages.splice(after + 1 + k, 0, { id })
  }
  return { ...doc, pages }
}

export function deletePage(doc: Doc, index: number): Doc {
  if (doc.pages.length <= 1) return doc
  const id = doc.pages[index].id
  const gone = doc.items.filter((i) => i.page === id).map((i) => i.id)
  const next = deleteItems({ ...doc, items: doc.items.map((i) => (i.page === id ? { ...i, locked: false } : i)) }, gone)
  return clampPaywall({ ...next, pages: next.pages.filter((p) => p.id !== id), guides: next.guides.filter((g) => g.page !== id) })
}

export function movePage(doc: Doc, from: number, to: number): Doc {
  if (from === to || to < 0 || to >= doc.pages.length) return doc
  const pages = [...doc.pages]
  const [page] = pages.splice(from, 1)
  pages.splice(to, 0, page)
  return { ...doc, pages }
}

function clampPaywall(doc: Doc): Doc {
  const n = doc.pages.length
  const pw = doc.paywall_page === null || n < 2 ? null : Math.min(Math.max(2, doc.paywall_page), n)
  return pw === doc.paywall_page ? doc : { ...doc, paywall_page: pw }
}

// ── threads ──────────────────────────────────────────────────────────────────

/** A lone text frame's thread, made for it (to type into). */
export function ensureThread(doc: Doc, frame: string): { doc: Doc; thread: string } {
  const found = doc.threads.find((t) => t.frames.includes(frame))
  if (found) return { doc, thread: found.id }
  const id = newId('s', allIds(doc))
  return { doc: { ...doc, threads: [...doc.threads, { id, frames: [frame], paras: [{ runs: [{ t: '' }] }] }] }, thread: id }
}

/** Thread `to` after `from`: text flows from one into the other. A frame
 *  with text of its own brings it along, after the thread's. */
export function link(doc: Doc, from: string, to: string): Doc {
  if (from === to) return doc
  const src = doc.threads.find((t) => t.frames.includes(from))
  const dst = doc.threads.find((t) => t.frames.includes(to))
  if (src && dst && src.id === dst.id) return doc
  const items = byId(doc)
  if (items.get(from)?.kind !== 'text' || items.get(to)?.kind !== 'text') return doc
  const base = src ?? { id: newId('s', allIds(doc)), frames: [from], paras: [{ runs: [{ t: '' }] }] }
  const at = base.frames.indexOf(from) + 1
  const moving = dst ? dst.frames : [to]
  const frames = [...base.frames.slice(0, at), ...moving, ...base.frames.slice(at)]
  const theirs = dst && dst.paras.some((p) => paraText(p)) ? dst.paras : []
  const merged: Thread = { id: base.id, frames, paras: [...base.paras, ...theirs] }
  const threads = doc.threads.filter((t) => t.id !== base.id && t.id !== dst?.id)
  return { ...doc, threads: [...threads, merged] }
}

/** Break a thread after `frame`: the frames after it are empty again. */
export function unlinkAfter(doc: Doc, frame: string): Doc {
  const t = doc.threads.find((x) => x.frames.includes(frame))
  if (!t) return doc
  const at = t.frames.indexOf(frame) + 1
  if (at >= t.frames.length) return doc
  return { ...doc, threads: doc.threads.map((x) => (x.id === t.id ? stripComp({ ...x, frames: x.frames.slice(0, at), comp: undefined }) : x)) }
}

export function setParas(doc: Doc, thread: string, paras: Para[]): Doc {
  return { ...doc, threads: doc.threads.map((t) => (t.id === thread ? { ...t, paras } : t)) }
}

// ── type ─────────────────────────────────────────────────────────────────────

export type Pos = [number, number] // [paragraph, UTF-16 offset]

const before = (a: Pos, b: Pos) => a[0] < b[0] || (a[0] === b[0] && a[1] < b[1])
export const order = (a: Pos, b: Pos): [Pos, Pos] => (before(b, a) ? [b, a] : [a, b])

/** Character attributes set on the text between `from` and `to` (the whole
 *  text when they're the same place and `whole`). */
export function applyChar(paras: Para[], from: Pos, to: Pos, attrs: CharAttrs): Para[] {
  const [a, b] = order(from, to)
  return paras.map((p, k) => {
    if (k < a[0] || k > b[0]) return p
    const start = k === a[0] ? a[1] : 0
    const end = k === b[0] ? b[1] : paraText(p).length
    if (start >= end && paraText(p).length) return p
    const runs = []
    const change = (r: CharAttrs) => {
      const merged = { ...('style' in attrs ? {} : r), ...attrs }
      if ('color' in attrs && !('swatch' in attrs)) delete merged.swatch
      return sparseChar(merged, !!p.style)
    }
    let at = 0
    for (const r of p.runs) {
      const s = Math.max(start, at), e = Math.min(end, at + r.t.length)
      if (e > s) {
        if (s > at) runs.push({ ...r, t: r.t.slice(0, s - at) })
        runs.push({ ...change(r), t: r.t.slice(s - at, e - at) })
        if (at + r.t.length > e) runs.push({ ...r, t: r.t.slice(e - at) })
      } else if (!paraText(p).length) runs.push({ ...change(r), t: '' })
      else runs.push(r)
      at += r.t.length
    }
    return { ...p, runs: mergeRuns(runs, !!p.style) }
  })
}

/** Paragraph attributes set on the paragraphs `from` to `to`. */
export function applyPara(paras: Para[], from: number, to: number, attrs: ParaAttrs): Para[] {
  const [a, b] = from <= to ? [from, to] : [to, from]
  return paras.map((p, k) => (k < a || k > b ? p : 'style' in attrs
    ? { ...sparsePara(attrs), runs: p.runs.map((r) => ({ t: r.t, ...(r.style ? { style: r.style } : {}) })) }
    : { runs: p.runs, ...sparsePara({ ...p, ...attrs }) }))
}

/** The attributes at a place: of the character before it (as typing takes). */
export function charAt(p: Para, offset: number): CharAttrs {
  let at = 0
  for (const r of p.runs) {
    if (offset <= at + r.t.length && (offset > at || r === p.runs[0])) return r
    at += r.t.length
  }
  return p.runs[p.runs.length - 1] ?? {}
}

// ── guides ───────────────────────────────────────────────────────────────────

export function addGuide(doc: Doc, page: string, axis: Guide['axis'], at: number): { doc: Doc; id: string } {
  const id = newId('g', allIds(doc))
  return { doc: { ...doc, guides: [...doc.guides, { id, page, axis, at: round(at) }] }, id }
}

export function moveGuide(doc: Doc, id: string, at: number): Doc {
  return { ...doc, guides: doc.guides.map((g) => (g.id === id ? { ...g, at: round(at) } : g)) }
}

export function deleteGuide(doc: Doc, id: string): Doc {
  return { ...doc, guides: doc.guides.filter((g) => g.id !== id) }
}
