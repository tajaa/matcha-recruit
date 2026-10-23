// A picture edit's recipe: a look, its sliders, a crop, a cut-out. The
// Picture Editor renders it (gl.ts) and uploads the result; the server keeps a
// clean copy on the edited picture (server/app/cappe/services/magazine/studio/
// recipe.py), cleaned exactly as `normalizeRecipe` cleans it — pinned by
// server/tests/cappe/fixtures/picture_recipe_cases.json.

import { round } from '../model/limits'

export const RECIPE_VERSION = 1

/** name: [lowest, highest, decimal places]; every slider's default is 0. */
export const SLIDERS = {
  exposure: [-4, 4, 2], // stops
  contrast: [-100, 100, 0],
  highlights: [-100, 100, 0],
  shadows: [-100, 100, 0],
  whites: [-100, 100, 0],
  blacks: [-100, 100, 0],
  temp: [-100, 100, 0],
  tint: [-100, 100, 0],
  vibrance: [-100, 100, 0],
  saturation: [-100, 100, 0],
  clarity: [-100, 100, 0],
  sharpen: [0, 100, 0],
  vignette: [-100, 100, 0],
  grain: [0, 100, 0],
  fade: [0, 100, 0],
  sh_hue: [0, 360, 0], // split toning: the shadows' tint and how much
  sh_amt: [0, 100, 0],
  hi_hue: [0, 360, 0], // and the highlights'
  hi_amt: [0, 100, 0],
} as const satisfies Record<string, readonly [number, number, number]>

export type Slider = keyof typeof SLIDERS
export const LOOK_KEYS = ['vivid', 'warm', 'cool', 'golden', 'teal', 'matte', 'film', 'chrome', 'faded', 'noir', 'mono',
  'sepia', 'dusk'] as const
export type LookKey = (typeof LOOK_KEYS)[number]

export type Crop = { x: number; y: number; w: number; h: number; angle: number; turn: 0 | 90 | 180 | 270;
  flip_h: boolean; flip_v: boolean }
export type CutPoint = { x: number; y: number; keep: boolean }
export type Cutout = { points: CutPoint[]; feather: number; invert: boolean }

export type Recipe = Partial<Record<Slider, number>> & { look?: LookKey; bw?: boolean; crop?: Crop; cutout?: Cutout }

export const TURNS = [0, 90, 180, 270] as const
export const ANGLE_MAX = 45
export const CROP_MIN = 0.02
export const MAX_POINTS = 32
export const FEATHER_MAX = 100
export const WHOLE: Crop = { x: 0, y: 0, w: 1, h: 1, angle: 0, turn: 0, flip_h: false, flip_v: false }

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)

function num(v: unknown, lo: number, hi: number, places: number): number | null {
  if (!isNum(v)) return null
  return round(Math.min(hi, Math.max(lo, v)), places)
}

function cleanCrop(raw: unknown): Crop | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  const w = num(r.w, CROP_MIN, 1, 4) ?? 1
  const h = num(r.h, CROP_MIN, 1, 4) ?? 1
  // The box stays on the picture: a box that runs off it is moved back on.
  const x = Math.min(num(r.x, 0, 1, 4) ?? 0, round(1 - w, 4))
  const y = Math.min(num(r.y, 0, 1, 4) ?? 0, round(1 - h, 4))
  const angle = num(r.angle, -ANGLE_MAX, ANGLE_MAX, 2) ?? 0
  const turn = (TURNS as readonly unknown[]).includes(r.turn) ? (r.turn as Crop['turn']) : 0
  const crop: Crop = { x, y, w, h, angle, turn, flip_h: r.flip_h === true, flip_v: r.flip_v === true }
  return isWhole(crop) ? null : crop
}

export const isWhole = (c: Crop) =>
  c.x === 0 && c.y === 0 && c.w === 1 && c.h === 1 && !c.angle && !c.turn && !c.flip_h && !c.flip_v

function cleanCutout(raw: unknown): Cutout | null {
  if (!raw || typeof raw !== 'object' || !Array.isArray((raw as { points?: unknown }).points)) return null
  const r = raw as { points: unknown[]; feather?: unknown; invert?: unknown }
  const points: CutPoint[] = []
  for (const p of r.points.slice(0, MAX_POINTS)) {
    if (!p || typeof p !== 'object') continue
    const q = p as Record<string, unknown>
    const x = num(q.x, 0, 1, 4), y = num(q.y, 0, 1, 4)
    if (x === null || y === null) continue
    points.push({ x, y, keep: q.keep !== false })
  }
  if (!points.some((p) => p.keep)) return null
  return { points, feather: num(r.feather, 0, FEATHER_MAX, 0) || 0, invert: r.invert === true }
}

/** A clean recipe: known keys only, numbers clamped and rounded, defaults left
 *  out (`{}` is "as it was"). Keys come out in the server's order. */
export function normalizeRecipe(raw: unknown): Recipe {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const r = raw as Record<string, unknown>
  const out: Recipe = {}
  if ((LOOK_KEYS as readonly unknown[]).includes(r.look)) out.look = r.look as LookKey
  for (const [name, [lo, hi, places]] of Object.entries(SLIDERS) as [Slider, readonly [number, number, number]][]) {
    const v = num(r[name], lo, hi, places)
    if (v) out[name] = v
  }
  if (r.bw === true) out.bw = true
  const crop = cleanCrop(r.crop)
  if (crop) out.crop = crop
  const cutout = cleanCutout(r.cutout)
  if (cutout) out.cutout = cutout
  return out
}

/** How much a picture W×H turned by `angle` must grow to still cover its own
 *  unturned box (straightening never shows past the picture's edge). */
export function coverScale(w: number, h: number, angle: number): number {
  const a = (Math.abs(angle) * Math.PI) / 180
  const c = Math.cos(a), s = Math.sin(a)
  return Math.max(c + (s * h) / w, c + (s * w) / h)
}

/** The picture's size once turned by a quarter turn (or not). */
export const turned = (w: number, h: number, turn: number): [number, number] => (turn === 90 || turn === 270 ? [h, w] : [w, h])

/** The size, in pixels, the recipe makes of a picture `w` × `h`. */
export function outputSize(w: number, h: number, recipe: Recipe): [number, number] {
  const c = recipe.crop
  if (!c) return [w, h]
  const [tw, th] = turned(w, h, c.turn)
  return [Math.max(1, Math.round(c.w * tw)), Math.max(1, Math.round(c.h * th))]
}
