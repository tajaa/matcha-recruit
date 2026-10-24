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
//
// Editorial controls, each off unless a paragraph or frame asks for it (so a
// story that uses none is set exactly as before):
//   * a drop cap (`dc` lines deep) sized so its cap height runs from the first
//     line's cap height to the last line's baseline, the lines beside it
//     narrowed; stored in `comp.caps`;
//   * widows and orphans (`kw`, `ko`): a column break that leaves too few of a
//     paragraph's lines on either side is moved; a runt (`runt`): words are
//     pushed down from the line before so the last one isn't left alone. Both
//     set the paragraph again a few times at most;
//   * text wrap (compose/wrap.ts): each line is set in the widest room the
//     frames and pictures it wraps leave at its height.

import { charOf, paraOf, type FullChar } from '../model/doc'
import { parentDoc, resolveParas } from '../model/identity'
import { round } from '../model/limits'
import type { Cap, Comp, Doc, Line, Para, TextItem, Thread } from '../model/types'
import { threadWraps, type Rect4, type Wraps } from './wrap'

export type Measure = {
  /** The width of `text` set in `c`, in pt. */
  width(c: FullChar, text: string): number
  /** The ascent and descent (positive) of `c`'s face at its size, in pt, and
   *  its cap height (70% of the size when not given). */
  metrics(c: FullChar): { asc: number; desc: number; cap?: number }
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

const startsWord = (toks: Tok[], j: number, i: number) => toks[j].kind === 'w' && (j === i || toks[j - 1].kind !== 'w')

/** The tokens of one line from `i`: as many as fit `avail` (and no more than
 *  `maxWords` words, when a runt is being mended). */
function fill(toks: Tok[], i: number, avail: number, text: string, m: Measure, maxWords = Infinity): Fill {
  let w = 0
  let words = 0
  let brk = -1 // the last token a line may end on
  for (let j = i; j < toks.length; j++) {
    const t = toks[j]
    if (t.kind === 'n') return { from: i, to: j - 1, next: j + 1, forced: true }
    if (t.kind === 's') {
      if (j > i) brk = j - 1
      w += t.w
      continue
    }
    if (startsWord(toks, j, i) && ++words > maxWords && brk >= i) return { from: i, to: brk, next: skipSpaces(toks, brk + 1), forced: false }
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

/** The widest room a column has between `top` and `bottom` once the
 *  obstacles overlapping that band are taken out (the leftmost of equals);
 *  null when they cover it. */
export function room(reg: { x: number; w: number }, obstacles: Rect4[], top: number, bottom: number): { x: number; w: number } | null {
  const lo = reg.x, hi = reg.x + reg.w
  const cuts = obstacles.filter((o) => o.y0 < bottom && o.y1 > top && o.x0 < hi && o.x1 > lo)
    .map((o) => [Math.max(lo, o.x0), Math.min(hi, o.x1)]).sort((a, b) => a[0] - b[0])
  let best: { x: number; w: number } | null = null
  let at = lo
  for (const [a, b] of [...cuts, [hi, hi]]) {
    if (a - at > (best?.w ?? 0) + 1e-9) best = { x: at, w: a - at }
    at = Math.max(at, b)
  }
  return best
}

const ALIGN: Record<string, number> = { l: 0, c: 1, r: 2, j: 3, ja: 3 }

/** How a paragraph is set again to mend a widow, orphan or runt: a column
 *  break before its line `breakAt`; at most `maxWords` words on line `line`. */
type Mend = { breakAt?: number; runt?: { line: number; words: number } }
/** A drop cap as composed: its paragraph, length, x and size; the line whose
 *  baseline it sits on (`ref`), else `below` pt under line `k0`'s. */
type CapDraft = { p: number; n: number; x: number; size: number; k0: number; ref: number; below: number }

/** A thread's lines through `frames` (its frames, in order), and whether
 *  text was left over. `wraps`: what each frame's text keeps away from. */
export function compose(paras: Para[], frames: TextItem[], m: Measure, wraps?: Wraps): { comp: Comp; overset: boolean } {
  const regs = regions(frames)
  const lines: Line[] = []
  const descs: number[] = []
  const regOf: number[] = []
  const words: number[] = []
  const forcedEnd: boolean[] = []
  const caps: CapDraft[] = []
  let r = 0
  let base: number | null = null // the last baseline in this region
  let space = 0 // space owed before the next line (after a paragraph)

  /** Set paragraph `p` from where the last one ended; false when text was left over. */
  const layPara = (p: number, mend: Mend): boolean => {
    const para = paras[p]
    const pa = paraOf(para)
    const text = para.runs.map((run) => run.t).join('')
    const toks = tokenize(para, m)
    let cap: { n: number; w: number; size: number; reg: number; x: number; lead: number } | null = null
    const capText = pa.dc >= 2 && toks[0]?.kind === 'w' ? [...text].slice(0, pa.dcn).join('') : ''
    if (capText && !/\s/.test(capText) && capText.length < text.length && capText.length <= toks[0].e) {
      // The cap's first characters leave the line: the rest of its word follows the cap.
      const c = toks[0].c
      const mt = m.metrics(c)
      const lead = pa.lead || c.size * 1.2
      const per = (m.metrics({ ...c, size: 1 }).cap ?? 0.7) || 0.7
      const size = ((pa.dc - 1) * lead + (mt.cap ?? 0.7 * c.size)) / per
      const n = capText.length
      if (toks[0].e > n) toks.splice(0, 1, { ...toks[0], e: n, w: 0, hyph: false }, { ...toks[0], s: n, w: m.width(c, text.slice(n, toks[0].e)) })
      else toks[0] = { ...toks[0], w: 0 }
      cap = { n, w: m.width({ ...c, size }, capText) + c.size * 0.35, size, reg: -1, x: 0, lead }
    }
    const k0 = lines.length
    let i = 0
    let first = true
    let lineNo = 0
    let trailingEmpty = toks.length === 0
    let drop = 0 // how far a line was moved down to find room beside what text wraps
    let broke = false
    while (i < toks.length || trailingEmpty) {
      if (r >= regs.length) return false
      const reg = regs[r]
      if (mend.breakAt === lineNo && !broke) {
        broke = true
        if (base !== null) { r++; base = null; drop = 0; continue }
      }
      const capped = cap && lineNo < pa.dc && (lineNo === 0 || cap.reg === r)
      const indent = pa.li + (first ? pa.fi : 0) + (capped ? cap!.w : 0)
      const obstacles = wraps?.[reg.f]
      let iv = { x: reg.x, w: reg.w }
      const c0 = toks[Math.min(i, toks.length - 1)]?.c ?? charOf(para.runs[0] ?? { t: '' })
      if (obstacles?.length) {
        const mt = m.metrics(c0)
        const lead = pa.lead || c0.size * 1.2
        const est = (base === null ? reg.y + mt.asc : base + lead + space) + drop
        if (est + mt.desc > reg.y + reg.h + 0.01) { r++; base = null; drop = 0; continue }
        const got = room(reg, obstacles, est - mt.asc, est + mt.desc)
        if (!got || got.w - indent - pa.ri < Math.max(2 * c0.size, 6)) { drop += Math.max(1, lead / 4); continue }
        iv = got
      }
      const avail = Math.max(1, iv.w - indent - pa.ri)
      let line: Fill
      if (i >= toks.length) line = { from: i, to: i - 1, next: i, forced: false }
      else line = fill(toks, i, avail, text, m, mend.runt?.line === lineNo ? mend.runt.words : Infinity)
      const own = toks.slice(line.from, line.to + 1).filter((t) => t.w || t.kind !== 'w' || !cap || t.s >= cap.n)
      let size = 0, asc = 0, desc = 0
      for (const t of own.length ? own : [{ c: c0 }]) {
        const mt = m.metrics(t.c)
        size = Math.max(size, t.c.size)
        asc = Math.max(asc, mt.asc)
        desc = Math.max(desc, mt.desc)
      }
      const lead = pa.lead || size * 1.2
      const baseline: number = (base === null ? reg.y + asc : base + lead + space) + drop
      if (baseline + desc > reg.y + reg.h + 0.01) {
        r++
        base = null
        drop = 0
        continue
      }
      if (obstacles?.length) {
        // Set taller than estimated: the room at its real height may be narrower.
        const got = room(reg, obstacles, baseline - asc, baseline + desc)
        if (!got || got.x > iv.x + 0.01 || got.x + got.w < iv.x + iv.w - 0.01) { drop += Math.max(1, lead / 4); continue }
      }
      // Trailing spaces end no line.
      let to = line.to
      while (to >= line.from && toks[to].kind === 's') to--
      const s = toks[line.from]?.s ?? (toks.length ? toks[toks.length - 1].e : 0)
      const e = to >= line.from ? toks[to].e : s
      const last = line.next >= toks.length && !(line.forced && line.next === toks.length)
      const code = pa.align === 'j' && (last || line.forced) ? 0 : ALIGN[pa.align]
      if (capped && lineNo === 0) { cap!.reg = r; cap!.x = iv.x + pa.li + pa.fi }
      lines.push([reg.f, p, s, e, round(iv.x + indent), round(baseline), round(avail), code])
      descs.push(desc)
      regOf.push(r)
      let n = 0
      for (let j = line.from; j <= to; j++) if (startsWord(toks, j, line.from)) n++
      words.push(n)
      forcedEnd.push(line.forced)
      base = baseline
      space = 0
      first = false
      drop = 0
      lineNo++
      trailingEmpty = line.forced && line.next === toks.length && !trailingEmpty && toks.length > 0
      if (i >= toks.length) break
      i = line.next
    }
    if (cap && cap.reg >= 0) {
      const deep = lines.length - k0 >= pa.dc && regOf[k0 + pa.dc - 1] === cap.reg
      caps.push({ p, n: cap.n, x: cap.x, size: cap.size, k0, ref: deep ? k0 + pa.dc - 1 : -1,
        below: deep ? 0 : (pa.dc - 1) * cap.lead })
    }
    return true
  }

  /** How to set paragraph `p` again (its lines from `k0`), or null when it's fine. */
  const mendFor = (p: number, k0: number, startedAtTop: boolean, mend: Mend): Mend | null => {
    const pa = paraOf(paras[p])
    const n = lines.length - k0
    if (n < 2) return null
    if (pa.runt > 1 && !mend.runt && !forcedEnd[k0 + n - 2] && words[k0 + n - 1] < pa.runt) {
      const keep = words[k0 + n - 2] - (pa.runt - words[k0 + n - 1])
      if (keep >= 1) return { ...mend, runt: { line: n - 2, words: keep } }
    }
    if (mend.breakAt !== undefined) return null
    const ko = Math.max(pa.ko, pa.dc >= 2 ? pa.dc : 1)
    const firstReg = regOf[k0]
    const lastReg = regOf[k0 + n - 1]
    if (firstReg === lastReg) return null
    const head = regOf.slice(k0, k0 + n).filter((x) => x === firstReg).length
    if (head < ko) return startedAtTop ? null : { ...mend, breakAt: 0 }
    const tail = regOf.slice(k0, k0 + n).filter((x) => x === lastReg).length
    if (tail < pa.kw) {
      const at = n - tail - (pa.kw - tail)
      const before = regOf.slice(k0, k0 + at).filter((x) => x === regOf[k0 + n - tail - 1]).length
      if (at >= 1 && (regOf[k0 + n - tail - 1] !== firstReg || before >= ko)) return { ...mend, breakAt: at }
      return startedAtTop ? null : { ...mend, breakAt: 0 }
    }
    return null
  }

  let overset = false
  for (let p = 0; p < paras.length; p++) {
    const pa = paraOf(paras[p])
    if (p > 0) space += pa.sb
    const saved = { r, base, space, n: lines.length, caps: caps.length }
    const restore = () => {
      r = saved.r; base = saved.base; space = saved.space
      for (const list of [lines, descs, regOf, words, forcedEnd]) list.length = saved.n
      caps.length = saved.caps
    }
    let mend: Mend = {}
    let good: Mend | null = null
    for (let tries = 0; ; tries++) {
      const fits = layPara(p, mend)
      if (!fits) {
        if (good) { restore(); layPara(p, good); break }
        overset = true
        break
      }
      const next = tries < 3 && (pa.kw > 1 || pa.ko > 1 || pa.runt > 1 || pa.dc >= 2)
        ? mendFor(p, saved.n, saved.base === null || regOf[saved.n] !== saved.r, mend) : null
      if (!next) break
      good = mend
      restore()
      mend = next
    }
    if (overset) break
    space = pa.sa
  }
  valign(lines, descs, regOf, regs, wraps)
  const out: Comp = { lines }
  if (caps.length) {
    out.caps = caps.map((c): Cap => [c.p, c.n, round(c.x), round((c.ref >= 0 ? lines[c.ref][5] : lines[c.k0][5]) + c.below), round(c.size)])
  }
  return { comp: out, overset }
}

/** Move each column's lines down (center, bottom) or spread them (justify);
 *  not in a frame whose text wraps something (its lines were set beside it). */
function valign(lines: Line[], descs: number[], regOf: number[], regs: Region[], wraps?: Wraps): void {
  const byReg = new Map<number, number[]>()
  regOf.forEach((r, k) => byReg.set(r, [...(byReg.get(r) ?? []), k]))
  for (const [r, ks] of byReg) {
    const reg = regs[r]
    if (reg.valign === 'top' || !ks.length || wraps?.[reg.f]?.length) continue
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
const sameCaps = (a: Cap[] | undefined, b: Cap[] | undefined) =>
  (a?.length ?? 0) === (b?.length ?? 0) && (a ?? []).every((c, k) => c.every((v, j) => v === b![k][j]))

/** What a thread's composition depends on besides its paragraphs: its
 *  frames' sizes and text options (not where they sit), and what their text
 *  wraps (compose/wrap.ts), which does move with them. */
const frameKey = (frames: TextItem[], wrapKey: string) =>
  frames.map((f) => `${f.w},${f.h},${f.cols},${f.gutter},${f.inset},${f.valign}`).join('|') + (wrapKey ? `#${wrapKey}` : '')

type Cached = { key: string; m: Measure; comp: Comp; overset: boolean }
const cache = new WeakMap<Para[], Cached>()

/** A thread composed, or its last composition when its paragraphs (the same
 *  array), its frames' sizes and what they wrap haven't changed: moving a
 *  frame doesn't set its text again. `fresh`: set it again anyway (a face has loaded). */
function composeCached(paras: Para[], frames: TextItem[], m: Measure, fresh: boolean,
  wrap: { wraps: Wraps | undefined; key: string }): { comp: Comp; overset: boolean } {
  const key = frameKey(frames, wrap.key)
  const hit = cache.get(paras)
  if (!fresh && hit && hit.key === key && hit.m === m) return hit
  const out = compose(paras, frames, m, wrap.wraps)
  cache.set(paras, { key, m, ...out })
  return out
}

/** Every thread composed; a thread whose lines didn't change keeps its object
 *  (so its pages aren't drawn again). Returns the doc and the threads overset. */
export function composeDoc(doc: Doc, m: Measure, fresh = false): { doc: Doc; overset: Set<string> } {
  const overset = new Set<string>()
  let changed = false
  const threads = doc.threads.map((t) => {
    const frames = threadFrames(doc, t)
    const { comp, overset: over } = composeCached(resolveParas(t.paras, doc.identity), frames, m, fresh, threadWraps(doc, frames))
    if (over) overset.add(t.id)
    if (sameLines(t.comp?.lines, comp.lines) && sameCaps(t.comp?.caps, comp.caps)) return t
    changed = true
    return { ...t, comp }
  })
  let identity = doc.identity
  if (identity?.parents.length) {
    const parents = identity.parents.map((p) => {
      const prepared = composeDoc(parentDoc(doc, p), m, fresh)
      for (const id of prepared.overset) overset.add(`${p.id}:${id}`)
      return prepared.doc.threads === p.threads ? p : { ...p, threads: prepared.doc.threads }
    })
    if (parents.some((p, k) => p !== identity!.parents[k])) { identity = { ...identity, parents }; changed = true }
  }
  return { doc: changed ? { ...doc, threads, ...(identity ? { identity } : {}) } : doc, overset }
}
