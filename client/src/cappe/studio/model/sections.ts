// The issue's stories (the issue board, ui/board/): a story starts at a page
// and runs to the next story's first page, so a story is always a run of
// pages and every page is in at most one. The server keeps the same list
// (schema._sections): one story per page, in page order, at most
// MAX_SECTIONS; pages before the first story belong to none.

import { newId } from './doc'
import { LIMITS } from './limits'
import type { Doc, Section } from './types'

/** A run of pages, [start, end): a story's, or the pages before the first. */
export type Run = { section: Section | null; start: number; end: number }

/** A story's name as the server keeps it: no control characters, trimmed,
 *  at most MAX_SECTION_NAME characters (counted whole, as Python does). */
export function cleanName(name: string): string {
  // eslint-disable-next-line no-control-regex -- the server drops these too (schema._DROP)
  const kept = name.replace(/[\u0000-\u0009\u000b-\u001f\u007f]/g, '').trim()
  return Array.from(kept).slice(0, LIMITS.MAX_SECTION_NAME).join('').trim()
}

/** The stories whose first page is in the document, in page order. */
export function sectionsOf(doc: Doc): Section[] {
  const at = new Map(doc.pages.map((p, i) => [p.id, i]))
  return (doc.sections ?? []).filter((s) => at.has(s.page)).sort((a, b) => at.get(a.page)! - at.get(b.page)!)
}

/** The document with these stories (the key left out when there are none). */
export function withSections(doc: Doc, sections: Section[]): Doc {
  if (sections.length) return { ...doc, sections }
  if (!('sections' in doc)) return doc
  const rest = { ...doc }
  delete rest.sections
  return rest
}

/** Every page in a run: the pages before the first story (when there are
 *  any), then each story to the next one's first page. */
export function runs(doc: Doc): Run[] {
  const n = doc.pages.length
  const list = sectionsOf(doc)
  if (!list.length) return n ? [{ section: null, start: 0, end: n }] : []
  const at = new Map(doc.pages.map((p, i) => [p.id, i]))
  const out: Run[] = []
  const first = at.get(list[0].page)!
  if (first > 0) out.push({ section: null, start: 0, end: first })
  list.forEach((s, k) => out.push({ section: s, start: at.get(s.page)!, end: k + 1 < list.length ? at.get(list[k + 1].page)! : n }))
  return out
}

/** Which story each page is in (by page id; null: before the first). */
function membership(doc: Doc): Map<string, string | null> {
  const out = new Map<string, string | null>()
  for (const r of runs(doc)) for (let i = r.start; i < r.end; i++) out.set(doc.pages[i].id, r.section?.id ?? null)
  return out
}

/** Stories again from pages in order and each page's story: each story
 *  starts at its first page. A story that would come back after another
 *  (which a move never makes) gives those pages to the story before them. */
function fromMembership(doc: Doc, order: Doc['pages'], member: Map<string, string | null>): Section[] {
  const byId = new Map(sectionsOf(doc).map((s) => [s.id, s]))
  const out: Section[] = []
  const closed = new Set<string | null>()
  let current: string | null | undefined
  for (const p of order) {
    let m = member.get(p.id) ?? null
    if (m !== current && closed.has(m)) m = current ?? null
    if (m !== current) {
      if (current !== undefined) closed.add(current)
      current = m
      const s = m === null ? undefined : byId.get(m)
      if (s) out.push({ ...s, page: p.id })
    }
  }
  return out
}

/** Start a story at page `index` (named "Story N" unless named). Nothing
 *  changes if one starts there already, or the issue has its most stories. */
export function startSection(doc: Doc, index: number, name?: string): Doc {
  const page = doc.pages[index]?.id
  const list = sectionsOf(doc)
  if (!page || list.some((s) => s.page === page) || list.length >= LIMITS.MAX_SECTIONS) return doc
  const id = newId('st', list.map((s) => s.id))
  const section = { id, page, name: cleanName(name ?? '') || `Story ${list.length + 1}` }
  const at = new Map(doc.pages.map((p, i) => [p.id, i]))
  return withSections(doc, [...list, section].sort((a, b) => at.get(a.page)! - at.get(b.page)!))
}

/** Rename a story (a name that is all spaces keeps the one it had). */
export function renameSection(doc: Doc, id: string, name: string): Doc {
  const list = sectionsOf(doc)
  const clean = cleanName(name)
  const s = list.find((x) => x.id === id)
  if (!s || !clean || s.name === clean) return doc
  return withSections(doc, list.map((x) => (x.id === id ? { ...x, name: clean } : x)))
}

/** Take a story's break away: its pages join the story before it. */
export function removeSection(doc: Doc, id: string): Doc {
  const list = sectionsOf(doc)
  return list.some((s) => s.id === id) ? withSections(doc, list.filter((s) => s.id !== id)) : doc
}

/** Move pages (by id, keeping their order) to `slot`, a place between the
 *  pages as they are now (0: before the first; the page count: after the
 *  last). A story moved whole stays a story, and lands between stories;
 *  other pages join the story they land in: the one of the page before them
 *  (`join` 'before'), or of the page after them ('after': dropped in front
 *  of a story's first page, they open that story). Pages keep every frame on
 *  them; the subscribers' page number stays where it was. */
export function moveBlock(doc: Doc, ids: Iterable<string>, slot: number, join: 'before' | 'after' = 'before'): Doc {
  const moving = new Set(ids)
  const block = doc.pages.filter((p) => moving.has(p.id))
  if (!block.length || block.length === doc.pages.length) return doc
  const member = membership(doc)
  const whole = new Set<string>()
  for (const r of runs(doc)) {
    if (!r.section) continue
    let all = true
    for (let i = r.start; i < r.end; i++) if (!moving.has(doc.pages[i].id)) all = false
    if (all) whole.add(r.section.id)
  }
  const rest = doc.pages.filter((p) => !moving.has(p.id))
  let at = doc.pages.slice(0, Math.max(0, Math.min(slot, doc.pages.length))).filter((p) => !moving.has(p.id)).length
  if (whole.size) {
    // A whole story lands between stories, never inside one, and after the
    // pages before the first story (only those can be in none).
    const front = rest.findIndex((p) => member.get(p.id) !== null)
    at = Math.max(at, front === -1 ? rest.length : front)
    if (at > 0 && at < rest.length && member.get(rest[at - 1].id) === member.get(rest[at].id)) {
      const m = member.get(rest[at - 1].id)
      while (at < rest.length && member.get(rest[at].id) === m) at++
    }
  }
  const order = [...rest.slice(0, at), ...block, ...rest.slice(at)]
  if (order.every((p, i) => p === doc.pages[i])) return doc
  // Pages that aren't a whole story join the run they land in: the page
  // before them (or, with none, the page after), or the other way round.
  const next = new Map(member)
  const loose = (id: string) => moving.has(id) && !whole.has(member.get(id) ?? '')
  const seq = join === 'before' ? order : [...order].reverse()
  seq.forEach((p, i) => {
    if (loose(p.id) && i > 0) next.set(p.id, next.get(seq[i - 1].id) ?? null)
  })
  const lead = seq.findIndex((p) => !loose(p.id))
  for (let i = 0; i < lead; i++) next.set(seq[i].id, next.get(seq[lead].id) ?? null)
  return withSections({ ...doc, pages: order }, fromMembership(doc, order, next))
}

/** The stories kept to an edit's pages: a story whose first page was
 *  deleted starts at the next of its pages still there (or goes, with none
 *  left); a story moves with its first page. Runs after every edit (the
 *  store), so nothing that deletes pages has to know about stories. */
export function keepSections(before: Doc, after: Doc): Doc {
  if (!after.sections?.length || (after.pages === before.pages && after.sections === before.sections)) return after
  const there = new Set(after.pages.map((p) => p.id))
  const old = runs(before)
  const fixed: Section[] = []
  const taken = new Set<string>()
  for (const s of after.sections) {
    let page: string | undefined = there.has(s.page) ? s.page : undefined
    if (!page) {
      const r = old.find((x) => x.section?.id === s.id)
      if (r) for (let i = r.start; i < r.end && !page; i++) if (there.has(before.pages[i].id)) page = before.pages[i].id
    }
    if (page && !taken.has(page)) {
      taken.add(page)
      fixed.push(page === s.page ? s : { ...s, page })
    }
  }
  const at = new Map(after.pages.map((p, i) => [p.id, i]))
  fixed.sort((a, b) => at.get(a.page)! - at.get(b.page)!)
  const list = fixed.slice(0, LIMITS.MAX_SECTIONS)
  const same = list.length === after.sections.length && list.every((s, i) => s === after.sections![i])
  return same ? after : withSections(after, list)
}
