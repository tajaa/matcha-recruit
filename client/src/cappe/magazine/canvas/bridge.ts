import type { StoryBlock } from '../../types'
import { cleanRt, type RtDoc } from './rt'

/** What the page in the editor's frame talks about (magazine/frame/).
 *  The frame runs scripts without our origin, so everything it sends is
 *  checked here before an editor acts on it: its source (the caller), each
 *  message's shape, every index, name and length. Whether a story has that
 *  block or field is checked again where the edit is applied (storyDoc). */

export type FrameTarget =
  | { kind: 'block'; story: string; block: number }
  | { kind: 'story'; story: string }
  | { kind: 'cover'; el: CoverEl }
  | { kind: 'contents' }
  | { kind: 'none' }

/** On an issue's cover: the photo, the masthead, the issue line or a cover line. */
export type CoverEl = 'photo' | 'masthead' | 'issue_line' | `line:${number}`

/** What the page is shown on: two pages as on a computer, or a phone. */
export type Device = 'spread' | 'phone'

export type MoveTarget = { kind: 'cover'; el: CoverEl } | { kind: 'overlay'; story: string; block: number; overlay: number }

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
  | { type: 'mz-key'; key: 'undo' | 'redo' | 'save' | 'delete' }

/** The longest plain words the page may send (a field's own limit is applied
 *  where the edit lands: storyDoc), and the largest rich document, as JSON:
 *  more than a whole story the server keeps (600 KB), so a document too big
 *  to save reaches the server and its message is what the owner sees; this
 *  only turns away absurd messages. */
export const MAX_VALUE = 20_000
export const MAX_DOC_JSON = 2_000_000
const MAX_BLOCK = 119
const INSERTABLE = new Set<StoryBlock['type']>(['text', 'photo', 'photos', 'quote', 'sidebar', 'qa', 'divider'])
const KEYS = new Set(['undo', 'redo', 'save', 'delete'])
const FIELD = /^(@(title|kicker|excerpt|byline)|[a-z_]+(\.\d{1,3}\.[a-z_]+)?|issue:(lines\.\d{1,2}\.(text|sub)|issue_line\.text|contents\.heading|(line|section):[0-9a-f-]{36}))$/

const obj = (v: unknown): Record<string, unknown> | null => (v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : null)
const int = (v: unknown, lo: number, hi: number): number | null => (Number.isInteger(v) && (v as number) >= lo && (v as number) <= hi ? v as number : null)
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? Math.max(0, Math.min(100, v)) : null)

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
      return s && b !== null ? { kind: 'block', story: s, block: b } : null
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
      const t = obj(d.target)
      if (t?.kind === 'overlay') {
        const s = story(t.story, ctx), b = int(t.block, 0, MAX_BLOCK)
        const m = typeof t.overlay === 'string' ? /^overlays\.(\d)$/.exec(t.overlay) : null
        return s && b !== null && m ? { type: 'mz-move', target: { kind: 'overlay', story: s, block: b, overlay: Number(m[1]) }, x, y, w } : null
      }
      const target = readTarget(t, ctx)
      return target?.kind === 'cover' && target.el !== 'photo' ? { type: 'mz-move', target, x, y, w } : null
    }
    case 'mz-focal': {
      const target = readTarget(d.target, ctx), x = num(d.x), y = num(d.y)
      return target && x !== null && y !== null ? { type: 'mz-focal', target, x, y } : null
    }
    case 'mz-key': return typeof d.key === 'string' && KEYS.has(d.key) ? { type: 'mz-key', key: d.key as 'undo' | 'redo' | 'save' | 'delete' } : null
    default: return null
  }
}

/** Where the editor turns the page back to after it re-renders: what is
 *  selected (found again on the new page), else the spread it was on. */
export type Place = { target: FrameTarget | null; spread: number }

export const sameTarget = (a: FrameTarget | null, b: FrameTarget | null) => JSON.stringify(a) === JSON.stringify(b)
