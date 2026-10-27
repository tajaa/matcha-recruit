// Merlin's edits (server/app/cappe/services/magazine/studio/merlin.py), checked
// against the document and applied. Pure: a round's edits become one
// `store.edit`, so Merlin's rounds stay one undo step (ui/ask/conversation.ts).
// The server has already cleaned each edit's fields; what is checked here is
// what only the document knows: the frame is there, on the page Merlin is
// working on (or selected), not locked, and of a kind that has the field. The
// words of a story are the writer's: a letter case changes only headings,
// captions and labels, and a new label is never body text.

import { composeDoc, type Measure } from '../../compose/compose'
import { allIds, newId, paraText, sparseChar, sparsePara } from '../../model/doc'
import { LIMITS } from '../../model/limits'
import { resolveParas } from '../../model/identity'
import { addItem, applyChar, applyPara, arrange, setParas, type Arrange } from '../../model/ops'
import type { CharAttrs, Doc, Fit, Item, Kind, ParaAttrs, Para, Role, Stroke, VAlign } from '../../model/types'

type ItemFields = Partial<{
  x: number; y: number; w: number; h: number; rot: number; opacity: number; hidden: boolean
  cols: number; gutter: number; inset: number; valign: VAlign; fill: string | null; stroke: Stroke | null
  radius: number; fit: Fit; zoom: number; fx: number; fy: number; color: string | null
}>
type TypeFields = Pick<CharAttrs, 'font' | 'wt' | 'it' | 'size' | 'track' | 'color' | 'u'>
  & Pick<ParaAttrs, 'align' | 'lead' | 'sb' | 'sa' | 'li' | 'ri' | 'fi' | 'dc' | 'dcn'>
export type LabelRole = Extract<Role, 'h1' | 'h2' | 'h3' | 'caption'>

export type MerlinOp =
  | ({ op: 'set'; id: string } & ItemFields)
  | ({ op: 'type'; id: string; paras?: number[] } & TypeFields)
  | { op: 'case'; id: string; paras?: number[]; to: 'upper' | 'lower' | 'title' }
  | ({ op: 'add'; kind: 'rect' | 'ellipse' | 'line' | 'text'; x: number; y: number; w: number; h: number
      to?: 'back' | 'front'; text?: string; role?: LabelRole; type?: TypeFields } & ItemFields)
  | { op: 'arrange'; id: string; to: Arrange }

/** Where Merlin works: the page it started on, what was selected then, and the
 *  font families the Studio can set. */
export type Scope = { page: string; selection: string[]; hasFamily: (family: string) => boolean }

/** The document after the edits, and a line for each edit made or skipped
 *  (sent with the next round, so Merlin knows what took). */
export type Applied = { doc: Doc; did: string[]; skipped: string[] }

const COMMON = ['x', 'y', 'w', 'h', 'rot', 'opacity', 'hidden'] as const
const OWN: Record<Kind, readonly (keyof ItemFields)[]> = {
  text: ['cols', 'gutter', 'inset', 'valign', 'fill', 'stroke'],
  image: ['fill', 'stroke', 'radius', 'fit', 'zoom', 'fx', 'fy'],
  rect: ['fill', 'stroke', 'radius'],
  ellipse: ['fill', 'stroke'],
  line: ['stroke'],
  graphic: ['color'],
}
const CHAR_FIELDS = ['font', 'wt', 'it', 'size', 'track', 'color', 'u'] as const
const PARA_FIELDS = ['align', 'lead', 'sb', 'sa', 'li', 'ri', 'fi', 'dc', 'dcn'] as const
const NOTE = 300 // the server keeps each note to this

const note = (s: string) => (s.length > NOTE ? `${s.slice(0, NOTE - 1)}…` : s)
const show = (op: MerlinOp) => JSON.stringify(op)

/** The fields of `op` an item of this kind takes (a line keeps a stroke; a
 *  graphic in its own colours takes none). */
function itemPatch(item: Item, op: ItemFields): Record<string, unknown> {
  const patch: Record<string, unknown> = {}
  for (const k of [...COMMON, ...OWN[item.kind]]) {
    const v = op[k]
    if (v === undefined) continue
    if (typeof v === 'number' && !Number.isFinite(v)) continue
    if (k === 'stroke' && v === null && item.kind === 'line') continue
    if (k === 'color' && (item.kind !== 'graphic' || item.color === null || typeof v !== 'string')) continue
    patch[k] = v
  }
  // A colour set by hand is no longer the magazine's swatch.
  if ('fill' in patch || 'color' in patch) patch.fill_swatch = undefined
  if ('stroke' in patch) patch.stroke_swatch = undefined
  return patch
}

function setItem(doc: Doc, id: string, patch: Record<string, unknown>): Doc {
  return { ...doc, items: doc.items.map((i) => (i.id === id ? ({ ...i, ...patch } as Item) : i)) }
}

function typeAttrs(op: TypeFields, hasFamily: Scope['hasFamily']): { char: CharAttrs; para: ParaAttrs } {
  const char: CharAttrs = {}
  const para: ParaAttrs = {}
  for (const k of CHAR_FIELDS) {
    const v = op[k]
    if (v === undefined || v === null) continue
    if (k === 'font' && !hasFamily(v as string)) continue
    ;(char as Record<string, unknown>)[k] = v
  }
  for (const k of PARA_FIELDS) if (op[k] !== undefined && op[k] !== null) (para as Record<string, unknown>)[k] = op[k]
  return { char, para }
}

/** The paragraphs an edit names (all of them when it names none). */
function which(paras: Para[], named?: number[]): number[] {
  const all = paras.map((_, k) => k)
  return named?.length ? named.filter((k) => k >= 0 && k < paras.length) : all
}

function restyle(paras: Para[], ks: number[], { char, para }: { char: CharAttrs; para: ParaAttrs }): Para[] {
  let out = paras
  for (const k of ks) {
    if (Object.keys(char).length) out = applyChar(out, [k, 0], [k, paraText(out[k]).length], char)
    if (Object.keys(para).length) out = applyPara(out, k, k, para)
  }
  return out
}

function recase(text: string, to: 'upper' | 'lower' | 'title', after: string): string {
  if (to === 'upper') return text.toLocaleUpperCase()
  if (to === 'lower') return text.toLocaleLowerCase()
  let out = ''
  let prev = after
  for (const ch of text) {
    out += prev === '' || /[\s(/"“‘–—-]/.test(prev) ? ch.toLocaleUpperCase() : ch.toLocaleLowerCase()
    prev = ch
  }
  return out
}

/** `op` applied to `doc`, with the frame it changed or made, or why it wasn't. */
function one(doc: Doc, op: MerlinOp, scope: Scope, inScope: (item: Item) => boolean): { doc: Doc; id: string } | string {
  if (op.op === 'add') {
    if (!doc.pages.some((p) => p.id === scope.page)) return 'the page is gone'
    if (op.kind === 'text' && (!op.text?.trim() || !op.role)) return 'a label needs words and a heading or caption role'
    const made = addItem(doc, op.kind, scope.page, { x: op.x, y: op.y, w: op.w, h: op.h })
    const item = made.doc.items.find((i) => i.id === made.id)!
    let next = setItem(made.doc, made.id, itemPatch(item, op))
    if (op.kind === 'text') {
      const { char, para } = typeAttrs(op.type ?? {}, scope.hasFamily)
      const p: Para = { ...sparsePara({ ...para, role: op.role }), runs: [{ ...sparseChar(char), t: op.text!.trim() }] }
      next = { ...next, threads: [...next.threads, { id: newId('s', allIds(next)), frames: [made.id], paras: [p] }] }
    }
    return { doc: op.to ? arrange(next, [made.id], op.to) : next, id: made.id }
  }
  const out = change(doc, op, scope, inScope)
  return typeof out === 'string' ? out : { doc: out, id: op.id }
}

function change(doc: Doc, op: Exclude<MerlinOp, { op: 'add' }>, scope: Scope, inScope: (item: Item) => boolean): Doc | string {
  const item = doc.items.find((i) => i.id === op.id)
  if (!item || !inScope(item)) return `${op.id} isn't on the page Merlin is working on`
  if (item.locked) return `${op.id} is locked`
  switch (op.op) {
    case 'set': {
      const patch = itemPatch(item, op)
      return Object.keys(patch).length ? setItem(doc, item.id, patch) : `none of those fields apply to a ${item.kind}`
    }
    case 'arrange':
      return arrange(doc, [item.id], op.to)
    case 'type':
    case 'case': {
      if (item.kind !== 'text') return `${op.id} isn't a text frame`
      const thread = doc.threads.find((t) => t.frames.includes(item.id))
      if (!thread || !thread.paras.some((p) => paraText(p))) return `${op.id} has no text`
      if (op.op === 'type') {
        const attrs = typeAttrs(op, scope.hasFamily)
        if (!Object.keys(attrs.char).length && !Object.keys(attrs.para).length) return 'no type the Studio can set'
        return setParas(doc, thread.id, restyle(thread.paras, which(thread.paras, op.paras), attrs))
      }
      // Body text is the writer's, letter for letter.
      const roles = resolveParas(thread.paras, doc.identity).map((p) => p.role ?? 'p')
      const ks = which(thread.paras, op.paras).filter((k) => roles[k] !== 'p')
      if (!ks.length) return `${op.id}'s text is body text, which keeps its letters`
      const paras = thread.paras.map((p, k) => {
        if (!ks.includes(k)) return p
        let before = ''
        return { ...p, runs: p.runs.map((r) => {
          const t = recase(r.t, op.to, before)
          before = r.t.slice(-1) || before
          return { ...r, t }
        }) }
      })
      return setParas(doc, thread.id, paras)
    }
  }
}

/** Every edit that can be made, in order. `touched`: the frame each edit
 *  changed or made (null for one skipped). */
export function applyOps(doc: Doc, ops: MerlinOp[], scope: Scope): Applied & { touched: (string | null)[] } {
  const at = new Set(scope.selection)
  const inScope = (i: Item) => i.page === scope.page || at.has(i.id)
  const did: string[] = []
  const skipped: string[] = []
  const touched: (string | null)[] = []
  let next = doc
  for (const op of ops) {
    const out = one(next, op, scope, inScope)
    if (typeof out === 'string') {
      skipped.push(note(`Skipped ${show(op)}: ${out}`))
      touched.push(null)
    } else {
      if (out.doc !== next) did.push(note(`Did ${show(op)}`))
      touched.push(out.id)
      next = out.doc
    }
  }
  return { doc: next, did, skipped, touched }
}

/** About how tall a thread's last frame would have to be to hold all its
 *  text as the edits set it, in pt (its frame made as tall as it can be). */
function roomFor(doc: Doc, thread: string, measure: Measure): number | null {
  const t = doc.threads.find((x) => x.id === thread)
  const last = t?.frames[t.frames.length - 1]
  const frame = doc.items.find((i) => i.id === last)
  if (!t || !frame) return null
  const tall = { ...doc, items: doc.items.map((i) => (i.id === last ? { ...i, h: LIMITS.COORD } : i)) }
  const lines = (composeDoc(tall, measure).doc.threads.find((x) => x.id === thread)?.comp?.lines ?? [])
    .filter((l) => l[0] === t.frames.length - 1)
  if (!lines.length) return null
  const base = lines[lines.length - 1][5]
  const step = lines.length > 1 ? base - lines[lines.length - 2][5] : base
  return Math.ceil((base + 0.3 * step) / 5) * 5
}

/** `applyOps`, keeping text that fitted its frames fitting: when an edit
 *  would leave a thread's text overflowing that didn't before, its type
 *  changes come out first, then everything else done to its frames, each
 *  noted with about how much room the text needed (so the next round can
 *  make the frame bigger or the type smaller). */
export function fitOps(doc: Doc, ops: MerlinOp[], scope: Scope, measure: Measure): Applied {
  const before = composeDoc(doc, measure).overset
  const left: string[] = []
  let keep = ops
  for (let pass = 0; ; pass++) {
    const out = applyOps(doc, keep, scope)
    const { overset } = composeDoc(out.doc, measure)
    const fresh = out.doc.threads.filter((t) => overset.has(t.id) && !before.has(t.id))
    if (!fresh.length || pass === 2) {
      // Past both passes, something else made it overflow (a picture moved over it): say so.
      const still = fresh.map((t) => note(`The text in ${t.frames[t.frames.length - 1]} doesn't fit its frame now.`))
      return { doc: out.doc, did: out.did, skipped: [...out.skipped, ...left, ...still] }
    }
    const frames = new Map(fresh.flatMap((t) => t.frames.map((f) => [f, t.id] as const)))
    keep = keep.filter((op, k) => {
      const id = out.touched[k]
      const culprit = id !== null && frames.has(id) && (pass === 1 || op.op === 'type' || op.op === 'add')
      if (culprit) {
        const room = roomFor(out.doc, frames.get(id)!, measure)
        const frame = out.doc.items.find((i) => i.id === id)
        left.push(note(`Skipped ${show(op)}: the text in ${id} would no longer fit its frame`
          + (room && frame ? ` (it would need about ${room} pt of height at ${Math.round(frame.w)} pt wide)` : '')
          + '; make the frame bigger or the type smaller'))
      }
      return !culprit
    })
  }
}
