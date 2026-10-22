import type { StoryBlock } from '../../types'
import { emptyRt, type RtDoc } from '../canvas/rt'
import { nearestWeight } from './fontStack'
import type { Design, GroupLayer, ImageLayer, Layer, Paint, PaintedLayer, ShapeKind, ShapeLayer, TextLayer } from './types'
import { MAX_LAYERS } from './types'

/** Everything the editor does to a design, as functions from one design to
 *  the next: the workspace's panels, the page's handles and keys all go
 *  through these, so each change is one step of the story's undo. Numbers
 *  are rounded as the server rounds them (design_schema.num), so a saved
 *  design compares equal to the one being edited. */

/** Half up to `places` decimals, never -0 (design_schema.num). */
export const round = (v: number, places = 1) => {
  const s = 10 ** places
  return Math.floor(v * s + 0.5) / s + 0
}
export const clampN = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))

/** Where a design lives: a picture of a block (an item of a photo group),
 *  or a designed page. */
export type ArtAt = { block: number; item: number | null }

export const designPath = (item: number | null) => (item === null ? 'design' : `items.${item}.design`)

export function designOf(b: StoryBlock | undefined, item: number | null): Design | null {
  if (!b) return null
  if (item !== null) return b.type === 'photos' ? b.items[item]?.design ?? null : null
  if (b.type === 'cover' || b.type === 'photo' || b.type === 'page') return b.design ?? null
  return null
}

/** Whether a block (or its item) is something a design can sit on. */
export function holdsDesign(b: StoryBlock | undefined, item: number | null): boolean {
  if (!b) return false
  if (item !== null) return b.type === 'photos' && !!b.items[item]
  return b.type === 'cover' || b.type === 'photo' || b.type === 'page'
}

/** The block with its design (or its item's) replaced. A picture's design
 *  with no layers left is none. */
export function withDesign(b: StoryBlock, item: number | null, design: Design | null): StoryBlock {
  if (b.type === 'page') return { ...b, design: { layers: design?.layers ?? [], background: design?.background ?? b.design.background } }
  const kept = design && design.layers.length ? design : null
  if (item !== null) {
    if (b.type !== 'photos') return b
    return { ...b, items: b.items.map((it, i) => (i === item ? { ...it, design: kept } : it)) }
  }
  if (b.type === 'cover' || b.type === 'photo') return { ...b, design: kept }
  return b
}

// ── reading ──────────────────────────────────────────────────────────────────

/** Every layer, children of groups included, bottom to top. */
export function* walk(layers: Layer[]): Generator<Layer> {
  for (const l of layers) {
    yield l
    if (l.kind === 'group') yield* walk(l.children)
  }
}

export const countLayers = (d: Design | null | undefined) => [...walk(d?.layers ?? [])].length

export function findLayer(d: Design | null | undefined, id: string): Layer | null {
  for (const l of walk(d?.layers ?? [])) if (l.id === id) return l
  return null
}

/** The group a layer is in (null: the design itself). */
export function parentOf(d: Design, id: string): GroupLayer | null {
  for (const l of walk(d.layers)) if (l.kind === 'group' && l.children.some((c) => c.id === id)) return l
  return null
}

const siblingsOf = (d: Design, id: string): Layer[] => parentOf(d, id)?.children ?? d.layers

/** A box in artboard percent. */
export type Box = { x: number; y: number; w: number; h: number }

/** A layer's box; a group's is around its children. */
export function boxOf(l: Layer): Box {
  if (l.kind !== 'group') return { x: l.x, y: l.y, w: l.w, h: l.h }
  return union(l.children.map(boxOf))
}

export function union(boxes: Box[]): Box {
  if (!boxes.length) return { x: 0, y: 0, w: 0, h: 0 }
  const x = Math.min(...boxes.map((b) => b.x)), y = Math.min(...boxes.map((b) => b.y))
  const r = Math.max(...boxes.map((b) => b.x + b.w)), btm = Math.max(...boxes.map((b) => b.y + b.h))
  return { x, y, w: r - x, h: btm - y }
}

// ── changing layers ──────────────────────────────────────────────────────────

/** `d` with `fn` applied to each layer whose id is in `ids` (inside groups too). */
export function mapLayers(d: Design, ids: Iterable<string>, fn: (l: Layer) => Layer): Design {
  const want = new Set(ids)
  const go = (layers: Layer[]): Layer[] => layers.map((l) => {
    const next = want.has(l.id) ? fn(l) : l
    return next.kind === 'group' ? { ...next, children: go(next.children) } : next
  })
  return { ...d, layers: go(d.layers) }
}

type Props<T> = Partial<Omit<T, 'kind' | 'id'>>
/** Properties to set on layers: any layer's, a text layer's, a picture's, a shape's. */
export type LayerPatch = Props<TextLayer> & Props<ImageLayer> & Props<ShapeLayer>

/** A patch of properties, for the layers of a kind that have them. */
export function patchLayers(d: Design, ids: Iterable<string>, patch: LayerPatch): Design {
  return mapLayers(d, ids, (l) => {
    const keys = Object.keys(patch).filter((k) => k in l || (l.kind !== 'group' && k === 'link'))
    if (!keys.length) return l
    const next = { ...l } as Record<string, unknown>
    for (const k of keys) next[k] = (patch as Record<string, unknown>)[k]
    if (next.kind === 'text') next.weight = nearestWeight(next.font as string, next.weight as number)
    return next as unknown as Layer
  })
}

/** A geometry change (the page's handles, a nudge): numbers clamped and
 *  rounded as the server keeps them. A group moves by moving its children. */
export type Geometry = { id: string; x?: number; y?: number; w?: number; h?: number; rot?: number; size?: number }

export function setGeometry(d: Design, changes: Geometry[]): Design {
  let next = d
  for (const c of changes) {
    const l = findLayer(next, c.id)
    if (!l) continue
    if (l.kind === 'group') {
      const b = boxOf(l)
      const dx = c.x === undefined ? 0 : c.x - b.x, dy = c.y === undefined ? 0 : c.y - b.y
      const sx = c.w && b.w ? c.w / b.w : 1, sy = c.h && b.h ? c.h / b.h : 1
      next = mapLayers(next, [...walk(l.children)].filter((x) => x.kind !== 'group').map((x) => x.id), (x) => {
        const g = x as PaintedLayer
        return {
          ...g,
          x: round(clampN(b.x + dx + (g.x - b.x) * sx, -100, 200)), y: round(clampN(b.y + dy + (g.y - b.y) * sy, -100, 200)),
          w: round(clampN(g.w * sx, 0.5, 400)), h: round(clampN(g.h * sy, 0.5, 400)),
          ...(g.kind === 'text' && sx !== 1 ? { size: round(clampN(g.size * sx, 0.5, 60)) } : {}),
        } as Layer
      })
      continue
    }
    next = mapLayers(next, [c.id], (x) => ({
      ...x,
      ...(c.x !== undefined ? { x: round(clampN(c.x, -100, 200)) } : {}),
      ...(c.y !== undefined ? { y: round(clampN(c.y, -100, 200)) } : {}),
      ...(c.w !== undefined ? { w: round(clampN(c.w, 0.5, 400)) } : {}),
      ...(c.h !== undefined ? { h: round(clampN(c.h, 0.5, 400)) } : {}),
      ...(c.rot !== undefined ? { rot: round(normAngle(c.rot)) } : {}),
      ...(c.size !== undefined && x.kind === 'text' ? { size: round(clampN(c.size, 0.5, 60)) } : {}),
    }) as Layer)
  }
  return next
}

export const normAngle = (a: number) => {
  let r = ((a + 180) % 360 + 360) % 360 - 180
  if (r === -180) r = 180
  return r
}

// ── adding and taking away ───────────────────────────────────────────────────

/** An id no layer of `d` has. */
export function newId(d: Design | null | undefined, prefix = 'l'): string {
  const taken = new Set([...walk(d?.layers ?? [])].map((l) => l.id))
  for (let i = taken.size + 1; ; i++) {
    const id = `${prefix}${i.toString(36)}`.slice(0, 12)
    if (!taken.has(id)) return id
  }
}

const NONE: Paint = { kind: 'none', color: '#000000', angle: 180, stops: [] }
const base = (id: string, name: string, box: Box) => ({
  id, name, ...box, rot: 0, flip_x: false, flip_y: false, opacity: 100, blend: 'normal' as const, hidden: false, locked: false,
  link: '', fill: NONE, stroke: { color: '#000000', width: 0, style: 'solid' as const }, radius: [0, 0, 0, 0] as [number, number, number, number],
  shadows: [], blur: 0,
})

/** Kinds of words to add, as a design tool offers them. */
export const TEXT_PRESETS = {
  heading: { label: 'Heading', text: 'Add a heading', font: 'heading', size: 9, weight: 700, leading: 1, w: 80 },
  subheading: { label: 'Subheading', text: 'Add a subheading', font: 'heading', size: 5, weight: 600, leading: 1.1, w: 70 },
  body: { label: 'Body text', text: 'Add a little bit of body text', font: 'body', size: 2.6, weight: 400, leading: 1.4, w: 60 },
  caption: { label: 'Caption', text: 'A caption', font: 'body', size: 1.8, weight: 500, leading: 1.3, w: 40 },
  kicker: { label: 'Kicker', text: 'KICKER', font: 'body', size: 1.8, weight: 700, leading: 1.2, w: 40 },
} as const
export type TextPreset = keyof typeof TEXT_PRESETS

const docOf = (text: string): RtDoc => (text ? { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] } : emptyRt())

export function newText(d: Design | null | undefined, preset: TextPreset = 'body', at?: { x: number; y: number }, light = true): TextLayer {
  const p = TEXT_PRESETS[preset]
  const box = { x: round(at ? at.x - p.w / 2 : (100 - p.w) / 2), y: round(at ? at.y : 40), w: p.w, h: 10 }
  return {
    ...base(newId(d, 't'), '', box), kind: 'text', rt: docOf(p.text), font: p.font, size: p.size, weight: p.weight, italic: false,
    color: light ? '#ffffff' : '#111111', align: 'center', valign: 'top', leading: p.leading,
    tracking: preset === 'kicker' ? 0.12 : 0, case: 'none', pad: 0, autosize: 'height',
  }
}

export const SHAPE_LABELS: Record<ShapeKind, string> = { rect: 'Rectangle', ellipse: 'Ellipse', line: 'Line' }

export function newShape(d: Design | null | undefined, shape: ShapeKind, opts: { square?: boolean; ratio?: number } = {}): ShapeLayer {
  // A square looks square on an artboard of any shape: its height is its
  // width times the artboard's width over its height.
  const w = shape === 'line' ? 60 : 30
  const h = shape === 'line' ? 2 : opts.square ? round(w * (opts.ratio ?? 1)) : 20
  const box = { x: round((100 - w) / 2), y: round((100 - h) / 2), w, h }
  return {
    ...base(newId(d, 's'), SHAPE_LABELS[shape], box), kind: 'shape', shape,
    fill: shape === 'line' ? NONE : { kind: 'solid', color: '#10b981', angle: 180, stops: [] },
    stroke: shape === 'line' ? { color: '#111111', width: 0.4, style: 'solid' } : { color: '#000000', width: 0, style: 'solid' },
  }
}

/** A picture laid on the artboard at its own shape: `ratio` is the
 *  picture's width over height, `art` the artboard's. */
export function newImage(d: Design | null | undefined, assetId: string, ratio = 1.5, art = 1.5, name = 'Picture'): ImageLayer {
  const w = 40
  const h = round(clampN((w / ratio) * art, 1, 100))
  return {
    ...base(newId(d, 'p'), name, { x: round((100 - w) / 2), y: round(clampN((100 - h) / 2, 0, 100)), w, h }),
    kind: 'image', asset_id: assetId, fit: 'cover', focal: { x: 50, y: 50 }, zoom: 100, filter: 'none',
  }
}

/** `d` with `layers` added on top (or above `after`). Null when the design
 *  would hold more than the server keeps. */
export function addLayers(d: Design | null | undefined, layers: Layer[], after?: string): Design | null {
  const base_ = d ?? { layers: [] }
  if (countLayers(base_) + layers.reduce((n, l) => n + countLayers({ layers: [l] }), 0) > MAX_LAYERS) return null
  if (after) {
    const sibs = siblingsOf(base_, after), i = sibs.findIndex((l) => l.id === after)
    if (i >= 0) return insertInto(base_, after, (list) => [...list.slice(0, i + 1), ...layers, ...list.slice(i + 1)])
  }
  return { ...base_, layers: [...base_.layers, ...layers] }
}

/** `d` with the list holding `id` rewritten by `fn`. */
function insertInto(d: Design, id: string, fn: (list: Layer[]) => Layer[]): Design {
  const parent = parentOf(d, id)
  if (!parent) return { ...d, layers: fn(d.layers) }
  return mapLayers(d, [parent.id], (g) => ({ ...(g as GroupLayer), children: fn((g as GroupLayer).children) }))
}

export function removeLayers(d: Design, ids: Iterable<string>): Design {
  const gone = new Set(ids)
  const go = (layers: Layer[]): Layer[] => layers.filter((l) => !gone.has(l.id)).flatMap((l): Layer[] => {
    if (l.kind !== 'group') return [l]
    const children = go(l.children)
    return children.length ? [{ ...l, children }] : []
  })
  return { ...d, layers: go(d.layers) }
}

/** Copies of the layers (new ids throughout), nudged so they show. */
export function cloneLayers(d: Design | null | undefined, layers: Layer[], offset = 2): Layer[] {
  let scratch: Design = { layers: [...(d?.layers ?? [])] }
  const copy = (l: Layer): Layer => {
    const id = newId(scratch, l.id.replace(/[0-9a-z]{0,3}$/, '').slice(0, 6) || 'l')
    scratch = { layers: [...scratch.layers, { ...l, id, ...(l.kind === 'group' ? { children: [] } : {}) } as Layer] }
    if (l.kind === 'group') return { ...l, id, children: l.children.map(copy) }
    return { ...l, id, x: round(l.x + offset), y: round(l.y + offset) } as Layer
  }
  return layers.map(copy)
}

export function duplicate(d: Design, ids: string[]): { design: Design; ids: string[] } {
  const picked = topLevel(d, ids)
  const copies = cloneLayers(d, picked)
  const next = addLayers(d, copies, picked[picked.length - 1]?.id)
  return next ? { design: next, ids: copies.map((c) => c.id) } : { design: d, ids }
}

/** The layers named, in stacking order, without any inside another named one. */
export function topLevel(d: Design, ids: string[]): Layer[] {
  const want = new Set(ids)
  const out: Layer[] = []
  const go = (layers: Layer[]) => layers.forEach((l) => {
    if (want.has(l.id)) out.push(l)
    else if (l.kind === 'group') go(l.children)
  })
  go(d.layers)
  return out
}

// ── order ────────────────────────────────────────────────────────────────────

export type Arrange = 'front' | 'forward' | 'backward' | 'back'

/** The layers moved up or down their stack (each in its own group). */
export function arrange(d: Design, ids: string[], how: Arrange): Design {
  const want = new Set(ids)
  const go = (layers: Layer[]): Layer[] => {
    let list = layers.map((l) => (l.kind === 'group' ? { ...l, children: go(l.children) } : l))
    const moving = list.filter((l) => want.has(l.id))
    if (!moving.length) return list
    const rest = list.filter((l) => !want.has(l.id))
    if (how === 'front') return [...rest, ...moving]
    if (how === 'back') return [...moving, ...rest]
    list = list.slice()
    const order = how === 'forward' ? [...list.keys()].reverse() : [...list.keys()]
    for (const i of order) {
      if (!want.has(list[i].id)) continue
      const j = how === 'forward' ? i + 1 : i - 1
      if (j < 0 || j >= list.length || want.has(list[j].id)) continue
      ;[list[i], list[j]] = [list[j], list[i]]
    }
    return list
  }
  return { ...d, layers: go(d.layers) }
}

/** A layer moved to sit just above (or below) another, the layers panel's
 *  drag: into the target's group. */
export function moveLayer(d: Design, id: string, target: string, where: 'above' | 'below'): Design {
  const l = findLayer(d, id)
  if (!l || id === target || (l.kind === 'group' && findLayer({ layers: l.children }, target))) return d
  const without = removeLayers(d, [id])
  if (!findLayer(without, target)) return d
  return insertInto(without, target, (list) => {
    const i = list.findIndex((x) => x.id === target)
    const at = where === 'above' ? i + 1 : i
    return [...list.slice(0, at), l, ...list.slice(at)]
  })
}

// ── groups ───────────────────────────────────────────────────────────────────

/** The layers (siblings, each kept in stacking order) put in a group where
 *  the topmost of them was. */
export function group(d: Design, ids: string[]): { design: Design; id: string | null } {
  const picked = topLevel(d, ids)
  if (picked.length < 2) return { design: d, id: null }
  const parent = parentOf(d, picked[0].id)?.id ?? null
  if (picked.some((l) => (parentOf(d, l.id)?.id ?? null) !== parent)) return { design: d, id: null }
  const id = newId(d, 'g')
  const g: GroupLayer = {
    id, kind: 'group', name: 'Group', ...boxOf({ kind: 'group', children: picked } as GroupLayer), rot: 0, flip_x: false, flip_y: false,
    opacity: 100, blend: 'normal', hidden: false, locked: false, link: '', children: picked,
  }
  const top = picked[picked.length - 1].id
  const gone = new Set(picked.map((l) => l.id))
  // They are siblings: the group takes the topmost's place, the others go.
  const design = insertInto(d, top, (list) => list.flatMap((x) => (x.id === top ? [g] : gone.has(x.id) ? [] : [x])))
  return { design, id }
}

export function ungroup(d: Design, id: string): { design: Design; ids: string[] } {
  const g = findLayer(d, id)
  if (!g || g.kind !== 'group') return { design: d, ids: [id] }
  const kids = g.children.map((c) => ({
    ...c, opacity: round((c.opacity * g.opacity) / 100, 0),
    ...(c.blend === 'normal' && g.blend !== 'normal' ? { blend: g.blend } : {}),
  }) as Layer)
  return { design: insertInto(d, id, (list) => list.flatMap((x) => (x.id === id ? kids : [x]))), ids: kids.map((k) => k.id) }
}

// ── alignment ────────────────────────────────────────────────────────────────

export type AlignHow = 'left' | 'center' | 'right' | 'top' | 'middle' | 'bottom'

/** One layer aligned to the artboard; several to the box around them. */
export function align(d: Design, ids: string[], how: AlignHow): Design {
  const picked = topLevel(d, ids)
  if (!picked.length) return d
  const frame = picked.length === 1 ? { x: 0, y: 0, w: 100, h: 100 } : union(picked.map(boxOf))
  return setGeometry(d, picked.map((l) => {
    const b = boxOf(l)
    switch (how) {
      case 'left': return { id: l.id, x: frame.x }
      case 'center': return { id: l.id, x: frame.x + (frame.w - b.w) / 2 }
      case 'right': return { id: l.id, x: frame.x + frame.w - b.w }
      case 'top': return { id: l.id, y: frame.y }
      case 'middle': return { id: l.id, y: frame.y + (frame.h - b.h) / 2 }
      case 'bottom': return { id: l.id, y: frame.y + frame.h - b.h }
    }
  }))
}

/** Three or more layers spaced evenly, across or down. */
export function distribute(d: Design, ids: string[], axis: 'x' | 'y'): Design {
  const picked = topLevel(d, ids).map((l) => ({ l, b: boxOf(l) }))
  if (picked.length < 3) return d
  const pos = (b: Box) => (axis === 'x' ? b.x : b.y), size = (b: Box) => (axis === 'x' ? b.w : b.h)
  picked.sort((a, b) => pos(a.b) - pos(b.b))
  const first = picked[0].b, last = picked[picked.length - 1].b
  const span = pos(last) + size(last) - pos(first)
  const gap = (span - picked.reduce((s, p) => s + size(p.b), 0)) / (picked.length - 1)
  let at = pos(first)
  return setGeometry(d, picked.map(({ l, b }) => {
    const g = { id: l.id, [axis]: at } as Geometry
    at += size(b) + gap
    return g
  }))
}
