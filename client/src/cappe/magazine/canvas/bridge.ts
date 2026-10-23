import type { StoryBlock } from '../../types'
import { cleanRt, type RtDoc } from './rt'

/** What the page in the editor's frame talks about (magazine/frame/).
 *  The frame runs scripts without our origin, so everything it sends is
 *  checked here before an editor acts on it: its source (the caller), each
 *  message's shape, every index, name and length. Whether a story has that
 *  block or field is checked again where the edit is applied (storyDoc). */

export type FrameTarget =
  // `item`: one picture of a photo group.
  | { kind: 'block'; story: string; block: number; item?: number }
  // Layers of the design on a block's picture (or its item's), or on a page.
  | { kind: 'layer'; story: string; block: number; item: number | null; ids: string[] }
  | { kind: 'story'; story: string }
  | { kind: 'cover'; el: CoverEl }
  | { kind: 'contents' }
  | { kind: 'none' }

/** On an issue's cover: the photo, the masthead, the issue line or a cover line. */
export type CoverEl = 'photo' | 'masthead' | 'issue_line' | `line:${number}`

/** What the page is shown on: two pages as on a computer, or a phone. */
export type Device = 'spread' | 'phone'

export type MoveTarget = { kind: 'cover'; el: CoverEl }

/** A layer moved, sized or turned on the page: its new box (artboard
 *  percent), its turn, and a text layer's type size when it was scaled. */
export type LayerChange = { id: string; x?: number; y?: number; w?: number; h?: number; rot?: number; size?: number; autosize?: 'none' }

export type FrameKey = 'undo' | 'redo' | 'save' | 'delete' | 'copy' | 'cut' | 'paste' | 'duplicate' | 'group' | 'ungroup'
  | 'front' | 'forward' | 'backward' | 'back'

export type FrameMessage =
  | { type: 'mz-ready' }
  | { type: 'mz-shown' }
  | { type: 'mz-place'; spread: number }
  | { type: 'mz-select'; target: FrameTarget }
  | { type: 'mz-editing'; on: boolean }
  | { type: 'mz-edit'; story: string; block: number; field: string; value: string; rich: false }
  | { type: 'mz-edit'; story: string; block: number; field: string; value: RtDoc; rich: true }
  | { type: 'mz-insert'; story: string; at: number; kind: StoryBlock['type'] }
  | { type: 'mz-pick'; story: string; block: number; item: number | null }
  | { type: 'mz-move'; target: MoveTarget; x: number; y: number; w: number | null }
  | { type: 'mz-focal'; target: FrameTarget; x: number; y: number }
  | { type: 'mz-key'; key: FrameKey }
  | { type: 'mz-layers'; story: string; block: number; item: number | null; changes: LayerChange[] }
  /** The heights the page measured for a design's words that grow (`autosize: 'height'`). */
  | { type: 'mz-heights'; story: string; block: number; item: number | null; heights: Record<string, number> }

/** The longest plain words the page may send (a field's own limit is applied
 *  where the edit lands: storyDoc), and the largest rich document, as JSON:
 *  more than a whole story the server keeps (600 KB), so a document too big
 *  to save reaches the server and its message is what the owner sees; this
 *  only turns away absurd messages. */
export const MAX_VALUE = 20_000
export const MAX_DOC_JSON = 2_000_000
const MAX_BLOCK = 119
const INSERTABLE = new Set<StoryBlock['type']>(['text', 'photo', 'photos', 'quote', 'sidebar', 'qa', 'divider'])
const KEYS = new Set<string>(['undo', 'redo', 'save', 'delete', 'copy', 'cut', 'paste', 'duplicate', 'group', 'ungroup', 'front',
  'forward', 'backward', 'back'])
const FIELD = /^(@(title|kicker|excerpt|byline)|[a-z_]+(\.\d{1,3}\.[a-z_]+)?|(items\.\d{1,2}\.)?design\.[a-z0-9]{1,12}|issue:(lines\.\d{1,2}\.(text|sub)|issue_line\.text|contents\.heading|(line|section):[0-9a-f-]{36}))$/
const LAYER_ID = /^[a-z0-9]{1,12}$/
const MAX_CHANGES = 200

const obj = (v: unknown): Record<string, unknown> | null => (v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : null)
const int = (v: unknown, lo: number, hi: number): number | null => (Number.isInteger(v) && (v as number) >= lo && (v as number) <= hi ? v as number : null)
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? Math.max(0, Math.min(100, v)) : null)
const between = (v: unknown, lo: number, hi: number): number | null => (typeof v === 'number' && Number.isFinite(v) ? Math.max(lo, Math.min(hi, v)) : null)

function layerIds(v: unknown): string[] | null {
  if (!Array.isArray(v) || !v.length || v.length > MAX_CHANGES) return null
  return v.every((id) => typeof id === 'string' && LAYER_ID.test(id)) ? [...new Set(v as string[])] : null
}

/** A layer's change, its numbers held to what the server keeps (it clamps them again). */
function layerChange(v: unknown): LayerChange | null {
  const c = obj(v)
  if (!c || typeof c.id !== 'string' || !LAYER_ID.test(c.id)) return null
  const out: LayerChange = { id: c.id }
  const take = (k: 'x' | 'y' | 'w' | 'h' | 'rot' | 'size', lo: number, hi: number) => {
    if (c[k] === undefined) return true
    const n = between(c[k], lo, hi)
    if (n === null) return false
    out[k] = n
    return true
  }
  if (!(take('x', -100, 200) && take('y', -100, 200) && take('w', 0.5, 400) && take('h', 0.5, 400) && take('rot', -180, 180)
    && take('size', 0.5, 60))) return null
  if (c.autosize === 'none') out.autosize = 'none'
  return out
}

/** The context a message is read in: the stories on the page. */
export type BridgeContext = { stories: ReadonlySet<string> }

function story(v: unknown, ctx: BridgeContext): string | null {
  return typeof v === 'string' && ctx.stories.has(v) ? v : null
}

function coverEl(v: unknown): CoverEl | null {
  if (v === 'photo' || v === 'masthead' || v === 'issue_line') return v
  return typeof v === 'string' && /^line:\d{1,2}$/.test(v) ? v as CoverEl : null
}

export function readTarget(v: unknown, ctx: BridgeContext): FrameTarget | null {
  const t = obj(v)
  if (!t) return null
  switch (t.kind) {
    case 'none': return { kind: 'none' }
    case 'contents': return { kind: 'contents' }
    case 'cover': { const el = coverEl(t.el); return el ? { kind: 'cover', el } : null }
    case 'story': { const s = story(t.story, ctx); return s ? { kind: 'story', story: s } : null }
    case 'block': {
      const s = story(t.story, ctx), b = int(t.block, 0, MAX_BLOCK)
      if (!s || b === null) return null
      if (t.item === undefined || t.item === null) return { kind: 'block', story: s, block: b }
      const item = int(t.item, 0, 11)
      return item === null ? null : { kind: 'block', story: s, block: b, item }
    }
    case 'layer': {
      const s = story(t.story, ctx), b = int(t.block, 0, MAX_BLOCK), ids = layerIds(t.ids)
      const item = t.item === null ? null : int(t.item, 0, 11)
      return s && b !== null && ids && (item !== null || t.item === null) ? { kind: 'layer', story: s, block: b, item, ids } : null
    }
    default: return null
  }
}

/** A rich field's document, cleaned to what the server keeps; null when it
 *  isn't one or is too large. */
function richValue(v: unknown): RtDoc | null {
  if (!obj(v)) return null
  let size = 0
  try { size = JSON.stringify(v).length } catch { return null }
  return size <= MAX_DOC_JSON ? cleanRt(v) : null
}

/** A message from the frame, checked; null for anything else. */
export function readMessage(data: unknown, ctx: BridgeContext): FrameMessage | null {
  const d = obj(data)
  if (!d || typeof d.type !== 'string') return null
  switch (d.type) {
    case 'mz-ready': case 'mz-shown': return { type: d.type }
    case 'mz-place': { const s = int(d.spread, 0, 999); return s === null ? null : { type: 'mz-place', spread: s } }
    case 'mz-select': { const t = readTarget(d.target, ctx); return t ? { type: 'mz-select', target: t } : null }
    case 'mz-editing': return typeof d.on === 'boolean' ? { type: 'mz-editing', on: d.on } : null
    case 'mz-edit': {
      const field = typeof d.field === 'string' && FIELD.test(d.field) ? d.field : null
      const value = d.rich === true ? richValue(d.value) : d.rich === false && typeof d.value === 'string' && d.value.length <= MAX_VALUE ? d.value : null
      if (!field || value === null) return null
      const edit = (story: string, block: number): FrameMessage => (typeof value === 'string'
        ? { type: 'mz-edit', story, block, field, value, rich: false }
        : { type: 'mz-edit', story, block, field, value, rich: true })
      if (field.startsWith('issue:')) return typeof value === 'string' ? edit('', -1) : null
      const s = story(d.story, ctx), b = int(d.block, -1, MAX_BLOCK)
      return s && b !== null ? edit(s, b) : null
    }
    case 'mz-insert': {
      const s = story(d.story, ctx), at = int(d.at, 0, MAX_BLOCK + 1)
      const kind = typeof d.kind === 'string' && INSERTABLE.has(d.kind as StoryBlock['type']) ? d.kind as StoryBlock['type'] : null
      return s && at !== null && kind ? { type: 'mz-insert', story: s, at, kind } : null
    }
    case 'mz-pick': {
      const s = story(d.story, ctx), b = int(d.block, 0, MAX_BLOCK)
      const item = d.item === null || d.item === undefined ? null : int(d.item, 0, 11)
      if (!s || b === null || (item === null && d.item !== null && d.item !== undefined)) return null
      return { type: 'mz-pick', story: s, block: b, item }
    }
    case 'mz-move': {
      const x = num(d.x), y = num(d.y), w = d.w === undefined || d.w === null ? null : num(d.w)
      if (x === null || y === null || (w === null && d.w !== undefined && d.w !== null)) return null
      const target = readTarget(d.target, ctx)
      return target?.kind === 'cover' && target.el !== 'photo' ? { type: 'mz-move', target, x, y, w } : null
    }
    case 'mz-focal': {
      const target = readTarget(d.target, ctx), x = num(d.x), y = num(d.y)
      return target && x !== null && y !== null ? { type: 'mz-focal', target, x, y } : null
    }
    case 'mz-key': return typeof d.key === 'string' && KEYS.has(d.key) ? { type: 'mz-key', key: d.key as FrameKey } : null
    case 'mz-layers': {
      const s = story(d.story, ctx), b = int(d.block, 0, MAX_BLOCK)
      const item = d.item === null ? null : int(d.item, 0, 11)
      if (!s || b === null || (item === null && d.item !== null) || !Array.isArray(d.changes) || d.changes.length > MAX_CHANGES) return null
      const changes = d.changes.map(layerChange)
      return changes.every((c): c is LayerChange => c !== null) && changes.length
        ? { type: 'mz-layers', story: s, block: b, item, changes } : null
    }
    case 'mz-heights': {
      const s = story(d.story, ctx), b = int(d.block, 0, MAX_BLOCK)
      const item = d.item === null ? null : int(d.item, 0, 11)
      const given = obj(d.heights)
      if (!s || b === null || (item === null && d.item !== null) || !given) return null
      const entries = Object.entries(given)
      if (entries.length > MAX_CHANGES) return null
      const heights: Record<string, number> = {}
      for (const [id, v] of entries) {
        const h = between(v, 0.5, 400)
        if (!LAYER_ID.test(id) || h === null) return null
        heights[id] = h
      }
      return { type: 'mz-heights', story: s, block: b, item, heights }
    }
    default: return null
  }
}

/** Where the editor turns the page back to after it re-renders: what is
 *  selected (found again on the new page), else the spread it was on. */
export type Place = { target: FrameTarget | null; spread: number }

export const sameTarget = (a: FrameTarget | null, b: FrameTarget | null) => JSON.stringify(a) === JSON.stringify(b)
