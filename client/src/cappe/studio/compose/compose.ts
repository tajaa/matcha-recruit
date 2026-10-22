// The composer: a thread's paragraphs broken into lines and flowed through its
// frames and their columns, frame to frame. What it decides is stored
// (`thread.comp`) and printed line by line by the server and the Studio
// (render/layoutRender.ts); no browser breaks a line again.
//
// v1 breaks greedily: as many words as fit, at spaces, after a hyphen or dash,
// and at a line break; a word longer than its line is cut where it must be.
// Auto leading is 120% of a line's largest type. The first line in a column
// sits its ascent below the column's top; space before and after paragraphs
// is dropped at the top of a column. Vertical justification moves a column's
// lines down (center, bottom) or spreads them (justify).

import { charOf, paraOf, type FullChar } from '../model/doc'
import { round } from '../model/limits'
import type { Comp, Doc, Line, Para, TextItem, Thread } from '../model/types'

export type Measure = {
  /** The width of `text` set in `c`, in pt. */
  width(c: FullChar, text: string): number
  /** The ascent and descent (positive) of `c`'s face at its size, in pt. */
  metrics(c: FullChar): { asc: number; desc: number }
}

type Tok = { s: number; e: number; kind: 'w' | 's' | 'n'; w: number; c: FullChar; hyph: boolean }
type Region = { f: number; x: number; y: number; w: number; h: number; valign: TextItem['valign'] }

const PIECES = /\n| +|[^ \n]+/g
const WORD_PARTS = /[^-–—]*[-–—]+|[^-–—]+/g

/** A paragraph as tokens: words (cut after hyphens), runs of spaces, line
 *  breaks; each measured in its run's type. */
export function tokenize(p: Para, m: Measure): Tok[] {
  const out: Tok[] = []
  let at = 0
  for (const run of p.runs) {
    const c = charOf(run)
    for (const piece of run.t.matchAll(PIECES)) {
      const s = at + piece.index!
      const text = piece[0]
      if (text === '\n') out.push({ s, e: s + 1, kind: 'n', w: 0, c, hyph: false })
      else if (text[0] === ' ') out.push({ s, e: s + text.length, kind: 's', w: m.width(c, text), c, hyph: false })
      else {
        for (const part of text.matchAll(WORD_PARTS)) {
          const ps = s + part.index!
          out.push({ s: ps, e: ps + part[0].length, kind: 'w', w: m.width(c, part[0]), c, hyph: /[-–—]$/.test(part[0]) })
        }
      }
    }
    at += run.t.length
  }
  return out
}

/** Cut a word token so that its first part fits `room` (at least one character). */
function cut(tok: Tok, text: string, room: number, m: Measure): [Tok, Tok] {
  const chars = [...text.slice(tok.s, tok.e)]
  let k = 1
  let w = m.width(tok.c, chars[0])
  while (k < chars.length) {
    const next = m.width(tok.c, chars.slice(0, k + 1).join(''))
    if (next > room) break
    w = next
    k++
  }
  const split = tok.s + chars.slice(0, k).join('').length
  return [{ ...tok, e: split, w, hyph: false },
    { ...tok, s: split, w: m.width(tok.c, text.slice(split, tok.e)) }]
}

type Fill = { from: number; to: number; next: number; forced: boolean }

/** The tokens of one line from `i`: as many as fit `avail`. */
function fill(toks: Tok[], i: number, avail: number, text: string, m: Measure): Fill {
  let w = 0
  let brk = -1 // the last token a line may end on
  for (let j = i; j < toks.length; j++) {
    const t = toks[j]
    if (t.kind === 'n') return { from: i, to: j - 1, next: j + 1, forced: true }
    if (t.kind === 's') {
      if (j > i) brk = j - 1
      w += t.w
      continue
    }
    if (w + t.w > avail + 0.01) {
      if (brk >= i) return { from: i, to: brk, next: skipSpaces(toks, brk + 1), forced: false }
      if (j === i) {
        const [head, tail] = cut(t, text, avail, m)
        toks.splice(j, 1, head, tail)
        return { from: i, to: j, next: j + 1, forced: false }
      }
      return { from: i, to: j - 1, next: j, forced: false }
    }
    w += t.w
    if (t.hyph && toks[j + 1]?.kind === 'w') brk = j
  }
  return { from: i, to: toks.length - 1, next: toks.length, forced: false }
}

function skipSpaces(toks: Tok[], j: number): number {
  while (toks[j]?.kind === 's') j++
  return j
}

function regions(frames: TextItem[]): Region[] {
  return frames.flatMap((f, k) => {
    const cw = (f.w - 2 * f.inset - f.gutter * (f.cols - 1)) / f.cols
    if (cw <= 1 || f.h - 2 * f.inset <= 1) return []
    return Array.from({ length: f.cols }, (_, c) => ({
      f: k, x: f.inset + c * (cw + f.gutter), y: f.inset, w: cw, h: f.h - 2 * f.inset, valign: f.valign,
    }))
  })
}

const ALIGN: Record<string, number> = { l: 0, c: 1, r: 2, j: 3, ja: 3 }

/** A thread's lines through `frames` (its frames, in order), and whether
 *  text was left over. */
export function compose(paras: Para[], frames: TextItem[], m: Measure): { comp: Comp; overset: boolean } {
  const regs = regions(frames)
  const lines: Line[] = []
  const descs: number[] = []
  const regOf: number[] = []
  let r = 0
  let base: number | null = null // the last baseline in this region
  let space = 0 // space owed before the next line (after a paragraph)
  let overset = false
  outer: for (let p = 0; p < paras.length; p++) {
    const para = paras[p]
    const pa = paraOf(para)
    const text = para.runs.map((run) => run.t).join('')
    const toks = tokenize(para, m)
    if (p > 0) space += pa.sb
    let i = 0
    let first = true
    let trailingEmpty = toks.length === 0
    while (i < toks.length || trailingEmpty) {
      if (r >= regs.length) {
        overset = true
        break outer
      }
      const reg = regs[r]
      const indent = pa.li + (first ? pa.fi : 0)
      const avail = Math.max(1, reg.w - indent - pa.ri)
      let line: Fill
      if (i >= toks.length) line = { from: i, to: i - 1, next: i, forced: false }
      else line = fill(toks, i, avail, text, m)
      const own = toks.slice(line.from, line.to + 1)
      const c0 = own[0]?.c ?? toks[Math.min(i, toks.length - 1)]?.c ?? charOf(para.runs[0] ?? { t: '' })
      let size = 0, asc = 0, desc = 0
      for (const t of own.length ? own : [{ c: c0 }]) {
        const mt = m.metrics(t.c)
        size = Math.max(size, t.c.size)
        asc = Math.max(asc, mt.asc)
        desc = Math.max(desc, mt.desc)
      }
      const lead = pa.lead || size * 1.2
      const baseline: number = base === null ? reg.y + asc : base + lead + space
      if (baseline + desc > reg.y + reg.h + 0.01) {
        r++
        base = null
        continue
      }
      // Trailing spaces end no line.
      let to = line.to
      while (to >= line.from && toks[to].kind === 's') to--
      const s = toks[line.from]?.s ?? (toks.length ? toks[toks.length - 1].e : 0)
      const e = to >= line.from ? toks[to].e : s
      const last = line.next >= toks.length && !(line.forced && line.next === toks.length)
      const code = pa.align === 'j' && (last || line.forced) ? 0 : ALIGN[pa.align]
      lines.push([reg.f, p, s, e, round(reg.x + indent), round(baseline), round(avail), code])
      descs.push(desc)
      regOf.push(r)
      base = baseline
      space = 0
      first = false
      trailingEmpty = line.forced && line.next === toks.length && !trailingEmpty && toks.length > 0
      if (i >= toks.length) break
      i = line.next
    }
    space = pa.sa
  }
  valign(lines, descs, regOf, regs)
  return { comp: { lines }, overset }
}

/** Move each column's lines down (center, bottom) or spread them (justify). */
function valign(lines: Line[], descs: number[], regOf: number[], regs: Region[]): void {
  const byReg = new Map<number, number[]>()
  regOf.forEach((r, k) => byReg.set(r, [...(byReg.get(r) ?? []), k]))
  for (const [r, ks] of byReg) {
    const reg = regs[r]
    if (reg.valign === 'top' || !ks.length) continue
    const lastK = ks[ks.length - 1]
    const free = reg.y + reg.h - (lines[lastK][5] + descs[lastK])
    if (free <= 0) continue
    ks.forEach((k, n) => {
      const shift = reg.valign === 'center' ? free / 2 : reg.valign === 'bottom' ? free
        : ks.length > 1 ? (free * n) / (ks.length - 1) : 0
      lines[k][5] = round(lines[k][5] + shift)
    })
  }
}

/** The text frames a thread flows through, in order. */
export function threadFrames(doc: Doc, thread: Thread): TextItem[] {
  const byId = new Map(doc.items.map((i) => [i.id, i]))
  return thread.frames.map((id) => byId.get(id)).filter((i): i is TextItem => i?.kind === 'text')
}

const sameLines = (a: Line[] | undefined, b: Line[]) =>
  !!a && a.length === b.length && a.every((ln, k) => ln.every((v, j) => v === b[k][j]))

/** What a thread's composition depends on besides its paragraphs: its
 *  frames' sizes and text options (not where they sit). */
const frameKey = (frames: TextItem[]) =>
  frames.map((f) => `${f.w},${f.h},${f.cols},${f.gutter},${f.inset},${f.valign}`).join('|')

type Cached = { key: string; m: Measure; comp: Comp; overset: boolean }
const cache = new WeakMap<Para[], Cached>()

/** A thread composed, or its last composition when its paragraphs (the same
 *  array) and its frames' sizes haven't changed: moving a frame doesn't set
 *  its text again. `fresh`: set it again anyway (a face has loaded). */
function composeCached(paras: Para[], frames: TextItem[], m: Measure, fresh: boolean): { comp: Comp; overset: boolean } {
  const key = frameKey(frames)
  const hit = cache.get(paras)
  if (!fresh && hit && hit.key === key && hit.m === m) return hit
  const out = compose(paras, frames, m)
  cache.set(paras, { key, m, ...out })
  return out
}

/** Forget every cached composition (a face finished loading). */
/** Every thread composed; a thread whose lines didn't change keeps its object
 *  (so its pages aren't drawn again). Returns the doc and the threads overset. */
export function composeDoc(doc: Doc, m: Measure, fresh = false): { doc: Doc; overset: Set<string> } {
  const overset = new Set<string>()
  let changed = false
  const threads = doc.threads.map((t) => {
    const frames = threadFrames(doc, t)
    const { comp, overset: over } = composeCached(t.paras, frames, m, fresh)
    if (over) overset.add(t.id)
    if (sameLines(t.comp?.lines, comp.lines)) return t
    changed = true
    return { ...t, comp }
  })
  return { doc: changed ? { ...doc, threads } : doc, overset }
}
