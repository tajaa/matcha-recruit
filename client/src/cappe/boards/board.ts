// The board's geometry, kept out of React so it can be tested: the view
// (pan and zoom), where new pins land, stacking order, and the bounds the
// server holds pins to (`limits.ts`).
//
// A pin is placed in board units; the view maps them to the screen as
// screen = board × zoom + (view.x, view.y).

import type { Pin, PinLayout } from './api'
import { COORD_MAX, ROTATION_MAX, SIZE_MAX, SIZE_MIN, Z_MAX } from './limits'

export interface View {
  x: number
  y: number
  zoom: number
}

export interface Point {
  x: number
  y: number
}

export const ZOOM_MIN = 0.2
export const ZOOM_MAX = 3
/** Past this, raising a pin renumbers the whole board 1…n instead of climbing. */
export const COMPACT_AT = 10000
/** How far each of several dropped things lands from the one before. */
export const CASCADE = 28
const SNAP_DEGREES = 3

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

export const clampCoord = (v: number) => clamp(Math.round(v * 10) / 10, -COORD_MAX, COORD_MAX)
export const clampSize = (v: number) => clamp(Math.round(v * 10) / 10, SIZE_MIN, SIZE_MAX)

/** Where a point on screen (relative to the board's box) is on the board. */
export function toBoard(view: View, sx: number, sy: number): Point {
  return { x: (sx - view.x) / view.zoom, y: (sy - view.y) / view.zoom }
}

/** Zoom by `factor`, keeping the board point under (sx, sy) where it is. */
export function zoomAt(view: View, factor: number, sx: number, sy: number): View {
  const zoom = clamp(view.zoom * factor, ZOOM_MIN, ZOOM_MAX)
  const k = zoom / view.zoom
  return { zoom, x: sx - (sx - view.x) * k, y: sy - (sy - view.y) * k }
}

/** A view that shows every pin in a `width` × `height` box, never past 100%. */
export function fitView(pins: Pin[], width: number, height: number, pad = 48): View {
  if (!pins.length || width <= 0 || height <= 0) return { x: pad, y: pad, zoom: 1 }
  const left = Math.min(...pins.map((p) => p.x))
  const top = Math.min(...pins.map((p) => p.y))
  const right = Math.max(...pins.map((p) => p.x + p.w))
  const bottom = Math.max(...pins.map((p) => p.y + p.h))
  const zoom = clamp(Math.min((width - pad * 2) / Math.max(1, right - left),
    (height - pad * 2) / Math.max(1, bottom - top), 1), ZOOM_MIN, 1)
  return {
    zoom,
    x: (width - (right - left) * zoom) / 2 - left * zoom,
    y: (height - (bottom - top) * zoom) / 2 - top * zoom,
  }
}

/** Where the `n`th of several new pins lands around `centre`. */
export function cascade(centre: Point, n: number, size: { w: number; h: number } = { w: 0, h: 0 }): Point {
  const step = (n % 10) * CASCADE
  return { x: clampCoord(centre.x - size.w / 2 + step), y: clampCoord(centre.y - size.h / 2 + step) }
}

export const topZ = (pins: Pin[]) => pins.reduce((m, p) => Math.max(m, p.z), 0)

export const layoutOf = (p: Pin): PinLayout =>
  ({ id: p.id, x: p.x, y: p.y, w: p.w, h: p.h, rotation: p.rotation, z: p.z })

/** Bring a pin to the front. Returns the board and the pins whose stacking
 *  changed (none when it already was in front). */
export function raise(pins: Pin[], id: string): { pins: Pin[]; changed: Pin[] } {
  const pin = pins.find((p) => p.id === id)
  const top = topZ(pins)
  if (!pin || (pin.z === top && pins.filter((p) => p.z === top).length === 1)) return { pins, changed: [] }
  if (top + 1 <= Math.min(COMPACT_AT, Z_MAX)) {
    const next = pins.map((p) => (p.id === id ? { ...p, z: top + 1 } : p))
    return { pins: next, changed: next.filter((p) => p.id === id) }
  }
  const order = [...pins].sort((a, b) => a.z - b.z || a.created_at.localeCompare(b.created_at))
    .filter((p) => p.id !== id)
  order.push(pin)
  const rank = new Map(order.map((p, i) => [p.id, i + 1]))
  const next = pins.map((p) => ({ ...p, z: rank.get(p.id) ?? p.z }))
  return { pins: next, changed: next }
}

/** A new size from a corner drag. Pictures keep their shape unless `free`. */
export function resized(pin: Pin, w: number, h: number, free = false): { w: number; h: number } {
  const keep = !free && (pin.kind === 'image' || (pin.kind === 'file' && !!pin.src) || (pin.kind === 'link' && !!pin.src))
  if (!keep) return { w: clampSize(w), h: clampSize(h) }
  const ratio = pin.w / pin.h
  let nw = clampSize(w)
  let nh = nw / ratio
  if (nh > SIZE_MAX || nh < SIZE_MIN) {
    nh = clampSize(nh)
    nw = clampSize(nh * ratio)
  }
  return { w: nw, h: Math.round(nh * 10) / 10 }
}

/** The angle (degrees, -180…180) from a pin's centre to a point, snapped
 *  to straight within a few degrees. */
export function angleTo(centre: Point, at: Point, offset = 0): number {
  let a = (Math.atan2(at.y - centre.y, at.x - centre.x) * 180) / Math.PI + 90 - offset
  a = ((((a + 180) % 360) + 360) % 360) - 180
  for (const straight of [0, 90, -90, 180, -180]) {
    if (Math.abs(a - straight) <= SNAP_DEGREES) a = straight === -180 ? 180 : straight
  }
  return clamp(Math.round(a * 10) / 10, -ROTATION_MAX, ROTATION_MAX)
}
