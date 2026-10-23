// Reading and building a paged story's document, as the server does
// (schema.py): spreads, a run's full attributes, sparse storage, new items.

import { FONT_BY_NAME, hasItalic, nearestWeight } from '../../magazine/design/fontStack'
import { CHAR_DEFAULTS, LIMITS, PARA_DEFAULTS, clamp, round } from './limits'
import type { Align, CharAttrs, Doc, Item, Kind, Para, ParaAttrs, Role, Run, Thread } from './types'

export type FullChar = { font: string; wt: number; it: boolean; size: number; track: number; color: string; u: boolean }
export type FullPara = { align: Align; li: number; ri: number; fi: number; sb: number; sa: number; lead: number; role: Role }

export const CHAR_KEYS = ['font', 'wt', 'it', 'size', 'track', 'color', 'u'] as const
export const PARA_KEYS = ['align', 'li', 'ri', 'fi', 'sb', 'sa', 'lead', 'role'] as const

/** A run's character attributes, every one present (as `schema.char_attrs`). */
export function charOf(r: CharAttrs): FullChar {
  const font = r.font && FONT_BY_NAME.has(r.font) ? r.font : CHAR_DEFAULTS.font
  const wt = nearestWeight(font, r.wt ?? CHAR_DEFAULTS.wt)
  return {
    font,
    wt,
    it: !!r.it && hasItalic(font, wt),
    size: round(clamp(r.size ?? CHAR_DEFAULTS.size, 1, LIMITS.SIZE_MAX)),
    track: Math.round(clamp(r.track ?? 0, LIMITS.TRACK_MIN, LIMITS.TRACK_MAX)),
    color: r.color && /^#[0-9a-f]{6}([0-9a-f]{2})?$/.test(r.color) ? r.color : CHAR_DEFAULTS.color,
    u: !!r.u,
  }
}

export function paraOf(p: ParaAttrs): FullPara {
  const li = round(clamp(p.li ?? 0, 0, LIMITS.INDENT_MAX))
  return {
    align: (LIMITS.ALIGNS as readonly string[]).includes(p.align ?? '') ? (p.align as Align) : 'l',
    li,
    ri: round(clamp(p.ri ?? 0, 0, LIMITS.INDENT_MAX)),
    fi: round(clamp(p.fi ?? 0, -li, LIMITS.INDENT_MAX)),
    sb: round(clamp(p.sb ?? 0, 0, LIMITS.INDENT_MAX)),
    sa: round(clamp(p.sa ?? 0, 0, LIMITS.INDENT_MAX)),
    lead: round(clamp(p.lead ?? 0, 0, LIMITS.LEAD_MAX)),
    role: (LIMITS.ROLES as readonly string[]).includes(p.role ?? '') ? (p.role as Role) : 'p',
  }
}

/** Only what differs from the defaults (the stored form). */
export function sparseChar(full: CharAttrs): CharAttrs {
  const c = charOf(full)
  const out: CharAttrs = {}
  for (const k of CHAR_KEYS) if (c[k] !== CHAR_DEFAULTS[k]) (out as Record<string, unknown>)[k] = c[k]
  return out
}

export function sparsePara(full: ParaAttrs): ParaAttrs {
  const p = paraOf(full)
  const out: ParaAttrs = {}
  for (const k of PARA_KEYS) if (p[k] !== PARA_DEFAULTS[k]) (out as Record<string, unknown>)[k] = p[k]
  return out
}

const sameAttrs = (a: CharAttrs, b: CharAttrs) => CHAR_KEYS.every((k) => a[k] === b[k])

/** Runs as the server keeps them: neighbours with the same type merged,
 *  empty ones gone (an empty paragraph keeps one, for its line's height). */
export function mergeRuns(runs: Run[]): Run[] {
  const out: Run[] = []
  let last: CharAttrs | null = null
  for (const r of runs) {
    const attrs = sparseChar(r)
    last = attrs
    if (!r.t) continue
    const prev = out[out.length - 1]
    if (prev && sameAttrs(prev, attrs)) prev.t += r.t
    else out.push({ t: r.t, ...attrs })
  }
  return out.length ? out : [{ t: '', ...(last ?? {}) }]
}

export const paraText = (p: Para) => p.runs.map((r) => r.t).join('')

/** The pages (indexes) on each spread: facing pages open on a right-hand page
 *  alone, then go in pairs. */
export function spreads(doc: Pick<Doc, 'pages' | 'facing'>): number[][] {
  const n = doc.pages.length
  if (!doc.facing) return doc.pages.map((_, i) => [i])
  const out: number[][] = n ? [[0]] : []
  for (let i = 1; i < n; i += 2) out.push(i + 1 < n ? [i, i + 1] : [i])
  return out
}

/** "left" or "right" for a facing page ("right" when pages don't face). */
export const pageSide = (doc: Pick<Doc, 'facing'>, index: number): 'left' | 'right' =>
  doc.facing && index % 2 === 1 ? 'left' : 'right'

export const pageIndex = (doc: Doc, id: string) => doc.pages.findIndex((p) => p.id === id)
export const itemById = (doc: Doc, id: string) => doc.items.find((i) => i.id === id)

export function threadOf(doc: Doc, frameId: string): { thread: Thread; index: number } | null {
  for (const thread of doc.threads) {
    const index = thread.frames.indexOf(frameId)
    if (index !== -1) return { thread, index }
  }
  return null
}

/** A fresh id: `prefix` and the next free number. */
export function newId(prefix: string, taken: Iterable<string>): string {
  const used = new Set(taken)
  let n = 1
  while (used.has(`${prefix}${n}`)) n++
  return `${prefix}${n}`
}

export const allIds = (doc: Doc) => [...doc.items.map((i) => i.id), ...doc.threads.map((t) => t.id),
  ...doc.pages.map((p) => p.id), ...doc.guides.map((g) => g.id)]

/** A new item of `kind` (the server's defaults). */
export function newItem(kind: Kind, page: string, id: string, box: { x: number; y: number; w: number; h: number }): Item {
  const base = { id, page, x: round(box.x), y: round(box.y), w: round(box.w), h: round(box.h), rot: 0, opacity: 100,
    locked: false, hidden: false, name: '' }
  switch (kind) {
    case 'text':
      return { ...base, kind, cols: 1, gutter: 12, inset: 0, valign: 'top', fill: null, stroke: null }
    case 'image':
      return { ...base, kind, asset_id: null, fit: 'fill', fx: 50, fy: 50, zoom: 100, fill: null, stroke: null, radius: 0,
        caption: '' }
    case 'rect':
      return { ...base, kind, fill: '#d9d4cc', stroke: null, radius: 0 }
    case 'ellipse':
      return { ...base, kind, fill: '#d9d4cc', stroke: null }
    case 'line':
      return { ...base, kind, stroke: { c: '#1a1a1a', w: 1 }, flip: false }
  }
}

/** A page size the Pages panel offers (points). */
export const PAGE_PRESETS: { key: string; label: string; w: number; h: number }[] = [
  { key: 'letter', label: 'Letter', w: 612, h: 792 },
  { key: 'a4', label: 'A4', w: 595.28, h: 841.89 },
  { key: 'magazine', label: 'Magazine (8.375 × 10.875 in)', w: 603, h: 783 },
  { key: 'tabloid', label: 'Tabloid', w: 792, h: 1224 },
  { key: 'square', label: 'Square', w: 612, h: 612 },
  { key: 'portrait', label: 'Portrait 4:5', w: 576, h: 720 },
]
