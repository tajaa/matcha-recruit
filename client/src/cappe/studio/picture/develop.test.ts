import { describe, expect, it } from 'vitest'
import { developPixel, grainNoise, hueRgb, outputUv, sourceUv } from './develop'
import { normalizeRecipe, type Crop, type Recipe } from './recipe'

const crop = (c: Partial<Crop>): Crop => normalizeRecipe({ crop: c }).crop!
const at = { x: 0.5, y: 0.5 }
const px = { x: 10, y: 10 }
const dev = (c: [number, number, number], r: Recipe, uv = at) => developPixel(c, normalizeRecipe(r), uv, px)

describe('where an output pixel comes from', () => {
  it('is the same place with no crop', () => {
    expect(sourceUv(0.25, 0.75, 400, 300)).toEqual({ x: 0.25, y: 0.75 })
  })

  it('undoes a crop, a quarter turn and the flips', () => {
    expect(sourceUv(0, 0, 400, 300, crop({ x: 0.5, y: 0.5, w: 0.5, h: 0.5 }))).toEqual({ x: 0.5, y: 0.5 })
    // Turned right: the output's top-left is the source's bottom-left.
    const r = sourceUv(0, 0, 400, 300, crop({ turn: 90 }))
    expect([r.x, r.y]).toEqual([0, 1])
    const f = sourceUv(0.1, 0.2, 400, 300, crop({ flip_h: true, flip_v: true }))
    expect([f.x, f.y].map((v) => +v.toFixed(6))).toEqual([0.9, 0.8])
  })

  it('straightens about the middle, grown so no edge shows', () => {
    const c = crop({ angle: 10 })
    const mid = sourceUv(0.5, 0.5, 400, 300, c)
    expect(mid.x).toBeCloseTo(0.5)
    expect(mid.y).toBeCloseTo(0.5)
    for (const [u, v] of [[0, 0], [1, 0], [0, 1], [1, 1]]) {
      const p = sourceUv(u, v, 400, 300, c)
      expect(p.x).toBeGreaterThanOrEqual(-1e-9)
      expect(p.x).toBeLessThanOrEqual(1 + 1e-9)
      expect(p.y).toBeGreaterThanOrEqual(-1e-9)
      expect(p.y).toBeLessThanOrEqual(1 + 1e-9)
    }
  })

  it('finds a source point in the output again (for the cut-out’s clicks)', () => {
    for (const c of [crop({}), crop({ x: 0.1, y: 0.2, w: 0.6, h: 0.5, angle: -12, turn: 270, flip_h: true }), crop({ turn: 180, flip_v: true, angle: 30 })]) {
      const back = outputUv(...(Object.values(sourceUv(0.3, 0.6, 640, 480, c)) as [number, number]), 640, 480, c)
      expect(back.x).toBeCloseTo(0.3)
      expect(back.y).toBeCloseTo(0.6)
    }
  })
})

describe('a developed pixel', () => {
  const grey: [number, number, number] = [0.5, 0.5, 0.5]
  const orange: [number, number, number] = [0.9, 0.5, 0.2]

  it('is unchanged by an empty recipe', () => {
    dev(orange, {}).forEach((v, i) => expect(v).toBeCloseTo(orange[i], 6))
  })

  it('is lighter with more exposure and warmer with more temperature', () => {
    expect(dev(grey, { exposure: 1 })[0]).toBeGreaterThan(0.6)
    const warm = dev(grey, { temp: 60 })
    expect(warm[0]).toBeGreaterThan(warm[2])
  })

  it('has more spread with contrast, less colour with less saturation, none in black and white', () => {
    const c = dev(orange, { contrast: 60 })
    expect(c[0] - c[2]).toBeGreaterThan(orange[0] - orange[2])
    const s = dev(orange, { saturation: -100 })
    expect(s[0]).toBeCloseTo(s[2], 6)
    const bw = dev(orange, { bw: true })
    expect(new Set(bw.map((v) => v.toFixed(6))).size).toBe(1)
  })

  it('lifts shadows and pulls highlights by how light it is', () => {
    expect(dev([0.2, 0.2, 0.2], { shadows: 100 })[0]).toBeGreaterThan(0.2)
    expect(dev([0.85, 0.85, 0.85], { highlights: -100 })[0]).toBeLessThan(0.85)
    expect(dev([0.02, 0.02, 0.02], { blacks: 100 })[0]).toBeGreaterThan(0.1)
  })

  it('darkens the corners, not the middle, with a vignette', () => {
    expect(dev(grey, { vignette: -100 }, { x: 0, y: 0 })[0]).toBeLessThan(0.2)
    expect(dev(grey, { vignette: -100 })[0]).toBeCloseTo(0.5, 6)
  })

  it('tints shadows and highlights, and fades', () => {
    const toned = dev([0.15, 0.15, 0.15], { sh_hue: 220, sh_amt: 100 })
    expect(toned[2]).toBeGreaterThan(toned[0])
    expect(dev([0, 0, 0], { fade: 100 })[0]).toBeCloseTo(0.1, 6)
  })

  it('has grain that is the same each time', () => {
    const a = dev(grey, { grain: 100 })
    expect(dev(grey, { grain: 100 })).toEqual(a)
    for (let k = 0; k < 50; k++) {
      const n = grainNoise(k * 7, k * 13)
      expect(n).toBeGreaterThanOrEqual(-0.5)
      expect(n).toBeLessThan(0.5)
    }
  })

  it('has its hues where a colour wheel has them', () => {
    expect(hueRgb(0)).toEqual([1, 0, 0])
    expect(hueRgb(120)).toEqual([0, 1, 0])
    expect(hueRgb(240)).toEqual([0, 0, 1])
  })
})
