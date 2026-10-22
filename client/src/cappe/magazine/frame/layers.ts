import type { FrameKey, FrameTarget, LayerChange } from '../canvas/bridge'
import { layersHtml, type DesignAsset } from '../design/designRender'
import type { Design } from '../design/types'
import { select } from './selection'
import { clamp, onPlace, place, post, state, ui } from './state'
import { blockOf, storyOf } from './targets'
import { editField } from './typing'

/** Designing on the page: the layers laid over a picture or a designed page
 *  (a design's `.mzd` box, server design_render.py). Clicking a layer
 *  selects it (the group it is in; ⌘-click or a double click reaches inside),
 *  Shift adds to the selection, and dragging on the picture draws a box
 *  around the layers to select. A selection gets handles: drag it to move,
 *  its corners and sides to size it (a picture or words keep their shape
 *  from a corner; Shift keeps any shape; Alt sizes from the middle), the
 *  knob above it to turn it (Shift: by 15°). Moving and sizing snap to the
 *  artboard's edges and middle and to the other layers, with a guide drawn
 *  where they line up. A double click on words types into them.
 *
 *  The page changes as you drag; the editor outside is told once, when you
 *  let go (`mz-layers`), and it checks every number again. When the editor
 *  changes a design itself (its panels), it sends the design (`mz-design`)
 *  and the layers are drawn here at once with the same renderer the server
 *  uses (design/designRender.ts), before the server's page arrives. */

type Rect = { left: number; top: number; width: number; height: number }
type LayerTarget = Extract<FrameTarget, { kind: 'layer' }>

const esc = (s: string) => (typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(s) : s.replace(/["\\]/g, '\\$&'))

/** The editor's zoom outside: handles stay the same size on screen. */
let unit = 1
export function setZoom(scale: number) {
  unit = scale > 0 ? 1 / scale : 1
  document.documentElement.style.setProperty('--mze-k', String(unit))
  place()
}

// ── reading the page ─────────────────────────────────────────────────────────

export const artOf = (el: Element | null) => el?.closest<HTMLElement>('.mzd[data-mzd]') ?? null
export function itemOfArt(art: Element): number | null {
  const m = /^items\.(\d+)\.design$/.exec(art.getAttribute('data-mzd') || '')
  return m ? Number(m[1]) : null
}

/** The artboard's box on screen: the whole picture, however it is cut. */
function artRect(art: HTMLElement): Rect {
  const r = (art.querySelector(':scope > .mzd__box') ?? art).getBoundingClientRect()
  return { left: r.left, top: r.top, width: r.width || 1, height: r.height || 1 }
}

/** The part of the artboard on show (a cover is cut to fit its page). */
function shown(art: HTMLElement): Rect {
  const a = artRect(art), c = art.getBoundingClientRect()
  const left = Math.max(a.left, c.left), top = Math.max(a.top, c.top)
  return { left, top, width: Math.min(a.left + a.width, c.right) - left, height: Math.min(a.top + a.height, c.bottom) - top }
}

/** The design's box for a target: `[data-mz-s] [data-mz-b] .mzd[data-mzd=path]`. */
export function artFor(t: { story: string; block: number; item: number | null }): HTMLElement | null {
  const path = t.item === null ? 'design' : `items.${t.item}.design`
  const story = document.querySelector(`[data-mz-s="${esc(t.story)}"]`)
  const block = story?.querySelector(`[data-mz-b="${t.block | 0}"]`)
  return block?.querySelector<HTMLElement>(`.mzd[data-mzd="${path}"]`) ?? null
}

export const layerEl = (art: Element, id: string) => art.querySelector<HTMLElement>(`[data-mzd-l="${esc(id)}"]`)

const isGroup = (el: Element) => el.classList.contains('mzd__g')
const painted = (el: HTMLElement): HTMLElement[] =>
  isGroup(el) ? Array.from(el.querySelectorAll<HTMLElement>('.mzd__l[data-mzd-l]')) : [el]
const num = (el: HTMLElement, v: string) => parseFloat(el.style.getPropertyValue(v))
const rotOf = (el: HTMLElement) => parseFloat(/rotate\((-?[\d.]+)deg\)/.exec(el.style.transform)?.[1] ?? '0') || 0

/** A layer's place in percent, as drawn now (a box that grows with its
 *  words has no height of its own: it is measured). */
function pct(art: HTMLElement, el: HTMLElement) {
  const a = artRect(art)
  const h = num(el, '--h')
  return { x: num(el, '--x') || 0, y: num(el, '--y') || 0, w: num(el, '--w') || 0, h: Number.isNaN(h) ? (el.offsetHeight / a.height) * 100 : h }
}

/** A layer's box on screen, before it is turned. */
function boxPx(art: HTMLElement, el: HTMLElement): Rect & { rot: number } {
  if (isGroup(el)) return { ...unionRects(painted(el).map((p) => turnedBounds(boxPx(art, p)))), rot: 0 }
  const a = artRect(art), p = pct(art, el)
  return { left: a.left + (p.x / 100) * a.width, top: a.top + (p.y / 100) * a.height, width: (p.w / 100) * a.width,
    height: (p.h / 100) * a.height, rot: rotOf(el) }
}

/** The upright box around a turned one. */
function turnedBounds(b: Rect & { rot: number }): Rect {
  if (!b.rot) return b
  const r = (b.rot * Math.PI) / 180, c = Math.abs(Math.cos(r)), s = Math.abs(Math.sin(r))
  const w = b.width * c + b.height * s, h = b.width * s + b.height * c
  const cx = b.left + b.width / 2, cy = b.top + b.height / 2
  return { left: cx - w / 2, top: cy - h / 2, width: w, height: h }
}

function unionRects(rs: Rect[]): Rect {
  if (!rs.length) return { left: 0, top: 0, width: 0, height: 0 }
  const l = Math.min(...rs.map((r) => r.left)), t = Math.min(...rs.map((r) => r.top))
  return { left: l, top: t, width: Math.max(...rs.map((r) => r.left + r.width)) - l, height: Math.max(...rs.map((r) => r.top + r.height)) - t }
}

const selectedLayers = (): { t: LayerTarget; art: HTMLElement; els: HTMLElement[] } | null => {
  const t = state.selected
  if (t.kind !== 'layer') return null
  const art = artFor(t)
  const els = art ? t.ids.map((id) => layerEl(art, id)).filter((e): e is HTMLElement => !!e) : []
  return art && els.length ? { t, art, els } : null
}

const targetFor = (art: HTMLElement, ids: string[]): LayerTarget => ({
  kind: 'layer', story: storyOf(art), block: blockOf(art), item: itemOfArt(art), ids,
})

/** The picture (or page) a design is on, as a target to select. */
function pictureTarget(art: HTMLElement): FrameTarget {
  const item = itemOfArt(art)
  return item === null ? { kind: 'block', story: storyOf(art), block: blockOf(art) } : { kind: 'block', story: storyOf(art), block: blockOf(art), item }
}

export function selectLayers(art: HTMLElement, ids: string[]) {
  const t = targetFor(art, ids)
  select(t, layerEl(art, ids[0]))
  post({ type: 'mz-select', target: t })
}

/** The layer a click on `el` selects: the outermost one inside its design
 *  (a group, not what is in it), or the innermost when reaching inside. */
function hitLayer(el: Element, deep: boolean): HTMLElement | null {
  const art = artOf(el)
  let hit = el.closest<HTMLElement>('[data-mzd-l]')
  if (!art || !hit || hit.hasAttribute('data-mzd-lock')) return null
  if (deep) return hit
  // A group already entered (one of its children selected) is reached into.
  const t = state.selected
  const entered = t.kind === 'layer' ? t.ids.map((id) => layerEl(art, id)?.parentElement?.closest('.mzd__g')).filter(Boolean) : []
  for (let up = hit.parentElement?.closest<HTMLElement>('[data-mzd-l]'); up && art.contains(up); up = up.parentElement?.closest<HTMLElement>('[data-mzd-l]')) {
    if (entered.includes(up)) break
    hit = up
  }
  return hit
}

// ── what is drawn over the page ─────────────────────────────────────────────

const frame = ui('div', 'mze-lsel')
const HANDLES = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'] as const
type Handle = (typeof HANDLES)[number]
const DIR: Record<Handle, [number, number]> = { nw: [-1, -1], n: [0, -1], ne: [1, -1], e: [1, 0], se: [1, 1], s: [0, 1], sw: [-1, 1], w: [-1, 0] }
const handles = Object.fromEntries(HANDLES.map((h) => [h, ui('span', `mze-h mze-h--${h}`)])) as Record<Handle, HTMLElement>
const knob = ui('span', 'mze-rot')
knob.title = 'Drag to turn (Shift: by 15°)'
const hover = ui('div', 'mze-lhov')
const guideV = ui('div', 'mze-guide mze-guide--v')
const guideH = ui('div', 'mze-guide mze-guide--h')
const marquee = ui('div', 'mze-marquee')
const outlines: HTMLElement[] = []
let hovered: HTMLElement | null = null
let busy = false // a drag in progress: the selection is drawn by it

function place1(el: HTMLElement, x: number, y: number) {
  el.style.display = 'block'
  el.style.left = `${x}px`
  el.style.top = `${y}px`
}

function drawBox(el: HTMLElement, b: Rect, rot = 0) {
  Object.assign(el.style, { display: 'block', left: `${b.left}px`, top: `${b.top}px`, width: `${b.width}px`, height: `${b.height}px`,
    transform: rot ? `rotate(${rot}deg)` : '' })
}

/** A point of a turned box: (dx, dy) in -1..1 from its middle. */
function pointOf(b: Rect & { rot: number }, dx: number, dy: number, out = 0) {
  const r = (b.rot * Math.PI) / 180, cx = b.left + b.width / 2, cy = b.top + b.height / 2
  const lx = (dx * b.width) / 2, ly = (dy * b.height) / 2 + (dy < 0 ? -out : 0)
  return { x: cx + lx * Math.cos(r) - ly * Math.sin(r), y: cy + lx * Math.sin(r) + ly * Math.cos(r) }
}

function hideSelection() {
  frame.style.display = knob.style.display = 'none'
  HANDLES.forEach((h) => { handles[h].style.display = 'none' })
  outlines.forEach((o) => { o.style.display = 'none' })
}

onPlace(() => {
  const hov = hovered && document.contains(hovered) ? hovered : null
  const sel = selectedLayers()
  if (hov && !sel?.els.includes(hov)) {
    const art = artOf(hov)
    if (art) { const b = boxPx(art, hov); drawBox(hover, b, b.rot) }
  } else hover.style.display = 'none'
  if (busy) return
  hideSelection()
  if (!sel) return
  const { art, els } = sel
  const typing = !!state.editing && els.some((e) => e.contains(state.editing))
  const single = els.length === 1 && !isGroup(els[0])
  const b = single ? boxPx(art, els[0]) : { ...unionRects(els.map((e) => turnedBounds(boxPx(art, e)))), rot: 0 }
  drawBox(frame, b, b.rot)
  frame.classList.toggle('mze-lsel--typing', typing)
  if (!single) {
    els.forEach((e, i) => {
      while (outlines.length <= i) outlines.push(ui('div', 'mze-lout'))
      const eb = boxPx(art, e)
      drawBox(outlines[i], eb, eb.rot)
    })
  }
  const locked = els.some((e) => e.hasAttribute('data-mzd-lock'))
  if (typing || locked) return
  const k = unit
  for (const h of HANDLES) {
    const [dx, dy] = DIR[h]
    if (!single && (dx === 0 || dy === 0)) continue // several at once: sized from the corners
    const p = pointOf(b, dx, dy)
    place1(handles[h], p.x, p.y)
  }
  if (single) {
    const p = pointOf(b, 0, -1, 26 * k)
    place1(knob, p.x, p.y)
  }
})

// ── snapping ─────────────────────────────────────────────────────────────────

const TOL = 6

/** Lines a box snaps to: the artboard's edges and middle, the other layers'. */
function snapLines(art: HTMLElement, skip: HTMLElement[]) {
  const s = shown(art)
  const xs = [s.left, s.left + s.width / 2, s.left + s.width], ys = [s.top, s.top + s.height / 2, s.top + s.height]
  art.querySelectorAll<HTMLElement>(':scope > [data-mzd-l]').forEach((el) => {
    if (skip.some((x) => x === el || x.contains(el) || el.contains(x))) return
    const b = turnedBounds(boxPx(art, el))
    xs.push(b.left, b.left + b.width / 2, b.left + b.width)
    ys.push(b.top, b.top + b.height / 2, b.top + b.height)
  })
  return { xs, ys, shown: s }
}

/** The smallest shift that lines one of `values` up with one of `lines`. */
function nearest(values: number[], lines: number[]): { shift: number; at: number } | null {
  let best: { shift: number; at: number } | null = null
  for (const v of values) for (const l of lines) {
    const d = l - v
    if (Math.abs(d) <= TOL * unit && (!best || Math.abs(d) < Math.abs(best.shift))) best = { shift: d, at: l }
  }
  return best
}

function showGuides(v: number | null, h: number | null, s: Rect) {
  if (v === null) guideV.style.display = 'none'
  else Object.assign(guideV.style, { display: 'block', left: `${v}px`, top: `${s.top}px`, height: `${s.height}px` })
  if (h === null) guideH.style.display = 'none'
  else Object.assign(guideH.style, { display: 'block', top: `${h}px`, left: `${s.left}px`, width: `${s.width}px` })
}

// ── gestures ─────────────────────────────────────────────────────────────────

type Start = { el: HTMLElement; x: number; y: number; w: number; h: number; rot: number; size: number; auto: boolean }

function startOf(art: HTMLElement, el: HTMLElement): Start {
  const p = pct(art, el)
  const t = el.querySelector<HTMLElement>(':scope > .mzd__t')
  const size = t ? parseFloat(/calc\(([\d.]+) \*/.exec(t.style.fontSize)?.[1] ?? '0') : 0
  return { el, ...p, rot: rotOf(el), size, auto: el.classList.contains('mzd__l--auto') }
}

function setPlace(el: HTMLElement, p: { x?: number; y?: number; w?: number; h?: number }) {
  if (p.x !== undefined) el.style.setProperty('--x', String(p.x))
  if (p.y !== undefined) el.style.setProperty('--y', String(p.y))
  if (p.w !== undefined) el.style.setProperty('--w', String(p.w))
  if (p.h !== undefined) el.style.setProperty('--h', String(p.h))
}

function setRot(el: HTMLElement, rot: number) {
  const flip = /scale\([^)]*\)/.exec(el.style.transform)?.[0]
  el.style.transform = [rot ? `rotate(${rot}deg)` : '', flip ?? ''].filter(Boolean).join(' ')
}

function setSize(el: HTMLElement, size: number) {
  const t = el.querySelector<HTMLElement>(':scope > .mzd__t')
  if (t) t.style.fontSize = `calc(${size} * var(--bw))`
}

const send = (art: HTMLElement, changes: LayerChange[]) => {
  if (changes.length) post({ type: 'mz-layers', story: storyOf(art), block: blockOf(art), item: itemOfArt(art), changes })
}

/** Follow a pointer from `e` until it is let go. */
function follow(e: PointerEvent, move: (dx: number, dy: number, ev: PointerEvent) => void, end: (moved: boolean) => void) {
  const x0 = e.clientX, y0 = e.clientY
  let moved = false
  const onMove = (ev: PointerEvent) => {
    const dx = ev.clientX - x0, dy = ev.clientY - y0
    if (!moved && Math.hypot(dx, dy) < 3 * unit) return
    moved = true
    busy = true
    move(dx, dy, ev)
  }
  const onUp = () => {
    removeEventListener('pointermove', onMove, true)
    removeEventListener('pointerup', onUp, true)
    removeEventListener('pointercancel', onUp, true)
    busy = false
    showGuides(null, null, { left: 0, top: 0, width: 0, height: 0 })
    // The click that ends a drag isn't a click on what is under it.
    if (moved) addEventListener('click', (ev) => { ev.stopPropagation(); ev.preventDefault() }, { capture: true, once: true })
    end(moved)
    place()
  }
  addEventListener('pointermove', onMove, true)
  addEventListener('pointerup', onUp, true)
  addEventListener('pointercancel', onUp, true)
}

/** Drag the selection: every layer in it moves together, snapping. */
function moveSelection(e: PointerEvent, art: HTMLElement, els: HTMLElement[]) {
  const leaves = els.flatMap(painted)
  const starts = leaves.map((el) => startOf(art, el))
  const a = artRect(art)
  const box0 = unionRects(els.map((el) => turnedBounds(boxPx(art, el))))
  const lines = snapLines(art, els)
  follow(e, (dx, dy, ev) => {
    let sx = dx, sy = dy
    if (ev.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) sy = 0; else sx = 0 }
    const l = box0.left + sx, t = box0.top + sy
    const snapX = ev.altKey ? null : nearest([l, l + box0.width / 2, l + box0.width], lines.xs)
    const snapY = ev.altKey ? null : nearest([t, t + box0.height / 2, t + box0.height], lines.ys)
    if (snapX) sx += snapX.shift
    if (snapY) sy += snapY.shift
    showGuides(snapX?.at ?? null, snapY?.at ?? null, lines.shown)
    for (const s of starts) setPlace(s.el, { x: s.x + (sx / a.width) * 100, y: s.y + (sy / a.height) * 100 })
    drawBox(frame, { ...box0, left: box0.left + sx, top: box0.top + sy })
    hideHandles()
    place()
  }, (moved) => {
    if (moved) send(art, starts.map((s) => ({ id: s.el.getAttribute('data-mzd-l')!, x: num(s.el, '--x'), y: num(s.el, '--y') })))
  })
}

function hideHandles() {
  HANDLES.forEach((h) => { handles[h].style.display = 'none' })
  knob.style.display = 'none'
  outlines.forEach((o) => { o.style.display = 'none' })
}

/** Size one layer from a handle, in its own (turned) axes. */
function resizeOne(e: PointerEvent, art: HTMLElement, el: HTMLElement, h: Handle) {
  const s = startOf(art, el), a = artRect(art), b = boxPx(art, el)
  const [hx, hy] = DIR[h]
  const r = (s.rot * Math.PI) / 180, cos = Math.cos(r), sin = Math.sin(r)
  const cx0 = b.left + b.width / 2, cy0 = b.top + b.height / 2
  const corner = hx !== 0 && hy !== 0
  const text = !!el.querySelector(':scope > .mzd__t')
  const picture = el.classList.contains('mzd__l--image')
  const lines = s.rot ? null : snapLines(art, [el])
  follow(e, (dx, dy, ev) => {
    // The pointer's move in the layer's own axes.
    let lx = dx * cos + dy * sin, ly = -dx * sin + dy * cos
    const fromMiddle = ev.altKey
    // A side being dragged snaps to a line (an upright layer only).
    if (lines && !fromMiddle) {
      const edgeX = hx === 0 ? null : (hx < 0 ? b.left : b.left + b.width) + lx
      const edgeY = hy === 0 ? null : (hy < 0 ? b.top : b.top + b.height) + ly
      const snapX = edgeX === null ? null : nearest([edgeX], lines.xs)
      const snapY = edgeY === null ? null : nearest([edgeY], lines.ys)
      if (snapX) lx += snapX.shift
      if (snapY) ly += snapY.shift
      showGuides(snapX?.at ?? null, snapY?.at ?? null, lines.shown)
    }
    const k = fromMiddle ? 2 : 1
    let w = hx ? b.width + hx * lx * k : b.width
    let ht = hy ? b.height + hy * ly * k : b.height
    // From a corner, words and pictures keep their shape; Shift keeps any.
    if (corner && (ev.shiftKey || text || picture)) {
      const f = Math.abs(w / b.width - 1) > Math.abs(ht / b.height - 1) ? w / b.width : ht / b.height
      w = b.width * f
      ht = b.height * f
    }
    w = Math.max(4 * unit, w)
    ht = Math.max(4 * unit, ht)
    // Where its middle goes: the opposite side stays put (from the middle: it does).
    const mx = fromMiddle ? 0 : (hx * (w - b.width)) / 2, my = fromMiddle ? 0 : (hy * (ht - b.height)) / 2
    const cx = cx0 + mx * cos - my * sin, cy = cy0 + mx * sin + my * cos
    const x = ((cx - w / 2 - a.left) / a.width) * 100, y = ((cy - ht / 2 - a.top) / a.height) * 100
    const p: { x: number; y: number; w: number; h?: number } = { x, y, w: (w / a.width) * 100 }
    if (text && corner) setSize(el, Math.round(s.size * (w / b.width) * 10) / 10)
    else if (!(text && s.auto && hy === 0)) p.h = (ht / a.height) * 100
    if (text && s.auto && hy !== 0 && !corner) el.classList.remove('mzd__l--auto')
    setPlace(el, p)
    drawBox(frame, { left: cx - w / 2, top: cy - ht / 2, width: w, height: ht }, s.rot)
    hideHandles()
    place()
  }, (moved) => {
    if (!moved) return
    const c: LayerChange = { id: el.getAttribute('data-mzd-l')!, x: num(el, '--x'), y: num(el, '--y'), w: num(el, '--w') }
    const h2 = num(el, '--h')
    if (!Number.isNaN(h2) && !(text && s.auto && hy === 0) && !(text && corner)) c.h = h2
    if (text && corner) c.size = parseFloat(/calc\(([\d.]+) \*/.exec(el.querySelector<HTMLElement>(':scope > .mzd__t')!.style.fontSize)?.[1] ?? String(s.size))
    if (text && s.auto && hy !== 0 && !corner) c.autosize = 'none'
    send(art, [c])
  })
}

/** Size several layers (or a group) from a corner: all of them scale
 *  together from the opposite corner, words with them. */
function resizeMany(e: PointerEvent, art: HTMLElement, els: HTMLElement[], h: Handle) {
  const a = artRect(art)
  const leaves = els.flatMap(painted).map((el) => startOf(art, el))
  const u = unionRects(els.map((el) => turnedBounds(boxPx(art, el))))
  const [hx, hy] = DIR[h]
  const ax = hx > 0 ? u.left : u.left + u.width, ay = hy > 0 ? u.top : u.top + u.height
  follow(e, (dx, dy) => {
    const f = Math.max(0.05, Math.max((u.width + hx * dx) / u.width, (u.height + hy * dy) / u.height))
    for (const s of leaves) {
      const left = a.left + (s.x / 100) * a.width, top = a.top + (s.y / 100) * a.height
      setPlace(s.el, {
        x: ((ax + (left - ax) * f - a.left) / a.width) * 100, y: ((ay + (top - ay) * f - a.top) / a.height) * 100,
        w: s.w * f, ...(s.auto ? {} : { h: s.h * f }),
      })
      if (s.size) setSize(s.el, Math.round(s.size * f * 10) / 10)
    }
    const w = u.width * f, ht = u.height * f
    drawBox(frame, { left: hx > 0 ? ax : ax - w, top: hy > 0 ? ay : ay - ht, width: w, height: ht })
    hideHandles()
    place()
  }, (moved) => {
    if (!moved) return
    send(art, leaves.map((s) => {
      const c: LayerChange = { id: s.el.getAttribute('data-mzd-l')!, x: num(s.el, '--x'), y: num(s.el, '--y'), w: num(s.el, '--w') }
      if (!s.auto) c.h = num(s.el, '--h')
      if (s.size) c.size = parseFloat(/calc\(([\d.]+) \*/.exec(s.el.querySelector<HTMLElement>(':scope > .mzd__t')!.style.fontSize)?.[1] ?? '0')
      return c
    }))
  })
}

/** Turn one layer by the knob above it. */
function rotate(e: PointerEvent, art: HTMLElement, el: HTMLElement) {
  const b = boxPx(art, el), cx = b.left + b.width / 2, cy = b.top + b.height / 2
  const r0 = rotOf(el), a0 = Math.atan2(e.clientY - cy, e.clientX - cx)
  follow(e, (_dx, _dy, ev) => {
    let r = r0 + ((Math.atan2(ev.clientY - cy, ev.clientX - cx) - a0) * 180) / Math.PI
    r = ((r + 180) % 360 + 360) % 360 - 180
    if (ev.shiftKey) r = Math.round(r / 15) * 15
    else if (Math.abs(r - Math.round(r / 90) * 90) < 3) r = Math.round(r / 90) * 90
    r = Math.round(r * 10) / 10
    setRot(el, r)
    drawBox(frame, b, r)
    hideHandles()
    place()
  }, (moved) => { if (moved) send(art, [{ id: el.getAttribute('data-mzd-l')!, rot: rotOf(el) }]) })
}

/** Drag across a picture: select the layers the box touches. */
function lasso(e: PointerEvent, art: HTMLElement) {
  const x0 = e.clientX, y0 = e.clientY
  follow(e, (dx, dy) => {
    const r = { left: Math.min(x0, x0 + dx), top: Math.min(y0, y0 + dy), width: Math.abs(dx), height: Math.abs(dy) }
    drawBox(marquee, r)
    const hits = Array.from(art.querySelectorAll<HTMLElement>(':scope > [data-mzd-l]:not([data-mzd-lock])')).filter((el) => {
      const b = turnedBounds(boxPx(art, el))
      return b.left < r.left + r.width && b.left + b.width > r.left && b.top < r.top + r.height && b.top + b.height > r.top
    })
    hits.forEach((el, i) => {
      while (outlines.length <= i) outlines.push(ui('div', 'mze-lout'))
      const b = boxPx(art, el)
      drawBox(outlines[i], b, b.rot)
    })
    outlines.slice(hits.length).forEach((o) => { o.style.display = 'none' })
    marquee.dataset.ids = hits.map((el) => el.getAttribute('data-mzd-l')).join(' ')
  }, () => {
    marquee.style.display = 'none'
    const ids = (marquee.dataset.ids || '').split(' ').filter(Boolean)
    delete marquee.dataset.ids
    if (ids.length) selectLayers(art, ids)
  })
}

// ── typing into words ────────────────────────────────────────────────────────

function typeInto(el: HTMLElement, at?: { x: number; y: number }) {
  const f = el.querySelector<HTMLElement>(':scope > [data-mz-f]')
  if (!f || el.hasAttribute('data-mzd-lock')) return
  editField(f, at)
  place()
}

// ── the design drawn again, from the editor outside ─────────────────────────

/** A design the editor changed: its layers drawn at once. Words being typed
 *  keep their field (only the box around them is restyled). */
export function drawDesign(t: { story: string; block: number; item: number | null }, design: Design,
  assets: Record<string, DesignAsset>) {
  const art = artFor(t)
  if (!art) return
  const html = layersHtml(design, assets, { edit: true, path: art.getAttribute('data-mzd') || 'design' })
  const typing = state.editing && art.contains(state.editing) ? state.editing.closest<HTMLElement>('[data-mzd-l]') : null
  const fresh = document.createElement('div')
  fresh.innerHTML = html
  if (typing) {
    const id = typing.getAttribute('data-mzd-l')!
    const next = fresh.querySelector<HTMLElement>(`[data-mzd-l="${esc(id)}"]`)
    if (next) {
      // Everything else is replaced; the box being typed in is kept, restyled.
      typing.setAttribute('style', next.getAttribute('style') || '')
      typing.className = next.className
      const t2 = next.querySelector<HTMLElement>(':scope > .mzd__t'), t1 = typing.querySelector<HTMLElement>(':scope > .mzd__t')
      if (t1 && t2) t1.setAttribute('style', t2.getAttribute('style') || '')
      next.replaceWith(typing)
    }
  }
  const probe = art.querySelector(':scope > .mzd__box')
  art.replaceChildren(...(probe ? [probe] : []), ...Array.from(fresh.childNodes))
  // Selected layers that went (deleted, ungrouped) are let go of.
  const sel = state.selected
  if (sel.kind === 'layer' && artFor(sel) === art) {
    const left = sel.ids.filter((id) => layerEl(art, id))
    if (left.length !== sel.ids.length) select(left.length ? { ...sel, ids: left } : pictureTarget(art), left.length ? layerEl(art, left[0]) : art.parentElement)
    else state.selectedEl = layerEl(art, sel.ids[0])
  }
  place()
}

/** Faces the editor picked: loaded into the page once. */
export function loadFonts(hrefs: string[]) {
  for (const href of hrefs) {
    if (!/^https:\/\/fonts\.googleapis\.com\/css2\?/.test(href) || document.querySelector(`link[href="${esc(href)}"]`)) continue
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = href
    document.head.appendChild(link)
  }
}

// ── keys ─────────────────────────────────────────────────────────────────────

let nudged: { art: HTMLElement; ids: Set<HTMLElement>; timer: ReturnType<typeof setTimeout> } | null = null

/** Keys while layers are selected (not typing). True when the key was theirs. */
export function layerKey(e: KeyboardEvent): boolean {
  const sel = selectedLayers()
  if (!sel) return false
  const { art, els } = sel
  const mod = e.metaKey || e.ctrlKey, k = (e.key || '').toLowerCase()
  const arrows: Record<string, [number, number]> = { arrowleft: [-1, 0], arrowright: [1, 0], arrowup: [0, -1], arrowdown: [0, 1] }
  if (arrows[k] && !mod) {
    const [dx, dy] = arrows[k], step = e.shiftKey ? 10 : 1, a = artRect(art)
    const leaves = els.flatMap(painted).filter((el) => !el.hasAttribute('data-mzd-lock'))
    for (const el of leaves) {
      const p = pct(art, el)
      setPlace(el, { x: clamp(p.x + (dx * step * 100) / a.width, -100, 200), y: clamp(p.y + (dy * step * 100) / a.height, -100, 200) })
    }
    // A run of nudges is one step: told once it stops.
    if (nudged) clearTimeout(nudged.timer)
    const all = new Set([...(nudged?.art === art ? nudged.ids : []), ...leaves])
    nudged = {
      art, ids: all,
      timer: setTimeout(() => {
        send(art, [...all].filter((el) => document.contains(el)).map((el) => ({ id: el.getAttribute('data-mzd-l')!, x: num(el, '--x'), y: num(el, '--y') })))
        nudged = null
      }, 350),
    }
    place()
    return true
  }
  if (e.key === 'Escape') {
    const up = els[0].parentElement?.closest<HTMLElement>('[data-mzd-l]')
    if (up && art.contains(up)) selectLayers(art, [up.getAttribute('data-mzd-l')!])
    else { const p = pictureTarget(art); select(p, art.parentElement); post({ type: 'mz-select', target: p }) }
    return true
  }
  if (e.key === 'Enter' && els.length === 1) {
    if (isGroup(els[0])) {
      const kids = Array.from(els[0].querySelectorAll<HTMLElement>(':scope > [data-mzd-l]')).map((el) => el.getAttribute('data-mzd-l')!)
      if (kids.length) selectLayers(art, kids)
    } else typeInto(els[0])
    return true
  }
  if (mod && k === 'a') {
    selectLayers(art, Array.from(art.querySelectorAll<HTMLElement>(':scope > [data-mzd-l]:not([data-mzd-lock])')).map((el) => el.getAttribute('data-mzd-l')!))
    return true
  }
  return false
}

/** The editor's own keys (copy, group, order…): the editor outside does them
 *  to what is selected. */
export function commandKey(e: KeyboardEvent): FrameKey | null {
  const mod = e.metaKey || e.ctrlKey
  if (!mod) return null
  const k = (e.key || '').toLowerCase()
  if (k === 'c') return 'copy'
  if (k === 'x') return 'cut'
  if (k === 'v') return 'paste'
  if (k === 'd') return 'duplicate'
  if (k === 'g') return e.shiftKey ? 'ungroup' : 'group'
  if (k === ']' || e.code === 'BracketRight') return e.altKey ? 'front' : 'forward'
  if (k === '[' || e.code === 'BracketLeft') return e.altKey ? 'back' : 'backward'
  return null
}

// ── wiring ───────────────────────────────────────────────────────────────────

export function startLayers() {
  // Pictures here are drawn on, never dragged out of the page (a drag on one
  // would end the gesture: the box that selects layers, a layer moved).
  document.addEventListener('dragstart', (e) => {
    if (e.target instanceof Element && e.target.closest('.mzd, .mz-frame, .mz-cover__media, .mz-page__art')) e.preventDefault()
  }, true)

  document.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return
    const t = e.target
    if (!(t instanceof Element) || t.closest('.mze-bar, .mze-menu')) return
    const sel = selectedLayers()
    // A handle or the knob of the selection.
    const h = HANDLES.find((x) => handles[x] === t)
    if (h && sel) {
      e.preventDefault(); e.stopPropagation()
      if (sel.els.length === 1 && !isGroup(sel.els[0])) resizeOne(e, sel.art, sel.els[0], h)
      else resizeMany(e, sel.art, sel.els, h)
      return
    }
    if (t === knob && sel?.els.length === 1) { e.preventDefault(); e.stopPropagation(); rotate(e, sel.art, sel.els[0]); return }
    if (t.closest('.mze-ui')) return
    // Typing into words: the click is the words'.
    if (state.editing && t.closest('[data-mz-f]') === state.editing) return
    const hit = hitLayer(t, e.metaKey || e.ctrlKey)
    if (hit) {
      const art = artOf(hit)!
      const id = hit.getAttribute('data-mzd-l')!
      e.stopPropagation()
      if (!(state.editing && hit.contains(state.editing))) e.preventDefault()
      if (e.shiftKey && sel && sel.art === art) {
        const ids = sel.t.ids.includes(id) ? sel.t.ids.filter((x) => x !== id) : [...sel.t.ids, id]
        if (ids.length) selectLayers(art, ids)
        else { const p = pictureTarget(art); select(p, art.parentElement); post({ type: 'mz-select', target: p }) }
        return
      }
      if (!sel || sel.art !== art || !sel.t.ids.includes(id)) selectLayers(art, [id])
      const now = selectedLayers()
      if (now && !now.els.some((x) => x.hasAttribute('data-mzd-lock'))) moveSelection(e, now.art, now.els)
      return
    }
    // A drag on a picture whose design is in hand (the picture or one of its
    // layers selected) draws a box to select layers with.
    const host = t.closest('.mz-frame, .mz-cover__media, .mz-page__art')
    const art = host?.querySelector<HTMLElement>(':scope > .mzd[data-mzd]')
    if (art && !t.closest('[data-mz-f], [data-mz-focal]') && inHand(art)) lasso(e, art)
  }, true)

  document.addEventListener('dblclick', (e) => {
    const t = e.target
    if (!(t instanceof Element) || t.closest('.mze-ui')) return
    const hit = hitLayer(t, true)
    if (!hit) return
    e.preventDefault()
    const art = artOf(hit)!
    if (hit.querySelector(':scope > .mzd__t')) {
      if (!state.editing || !hit.contains(state.editing)) {
        selectLayers(art, [hit.getAttribute('data-mzd-l')!])
        typeInto(hit, { x: e.clientX, y: e.clientY })
      }
    } else selectLayers(art, [hit.getAttribute('data-mzd-l')!])
  }, true)

  document.addEventListener('pointermove', (e) => {
    if (busy || e.buttons) return
    const t = e.target instanceof Element ? hitLayer(e.target, e.metaKey || e.ctrlKey) : null
    if (t !== hovered) { hovered = t; place() }
  }, { passive: true })
}

/** Whether a design's picture (or one of its layers) is what is selected. */
function inHand(art: HTMLElement): boolean {
  const t = state.selected
  if (t.kind === 'layer') return artFor(t) === art
  if (t.kind !== 'block' || t.story !== storyOf(art) || t.block !== blockOf(art)) return false
  return (t.item ?? null) === itemOfArt(art)
}
