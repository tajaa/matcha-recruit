import { describe, expect, it } from 'vitest'
import cases from '../../../../../server/tests/cappe/fixtures/picture_recipe_cases.json'
import { LOOKS, withLook } from './looks'
import { LOOK_KEYS, SLIDERS, coverScale, normalizeRecipe, outputSize, turned } from './recipe'

describe('a recipe', () => {
  it('is cleaned exactly as the server cleans it', () => {
    expect(cases.length).toBeGreaterThan(10)
    for (const c of cases) expect([c.name, normalizeRecipe(c.raw)]).toEqual([c.name, c.clean])
  })

  it('sets the size of what it makes', () => {
    expect(outputSize(3000, 2000, {})).toEqual([3000, 2000])
    expect(outputSize(3000, 2000, normalizeRecipe({ crop: { w: 0.5, h: 0.25 } }))).toEqual([1500, 500])
    expect(outputSize(3000, 2000, normalizeRecipe({ crop: { turn: 90, w: 0.5, h: 0.5 } }))).toEqual([1000, 1500])
    expect(turned(30, 20, 270)).toEqual([20, 30])
    expect(coverScale(100, 100, 0)).toBe(1)
    expect(coverScale(100, 100, 45)).toBeCloseTo(Math.SQRT2)
  })
})

describe('the looks', () => {
  it('are the ones the server knows, each within its sliders', () => {
    expect(LOOKS.map((l) => l.key)).toEqual([...LOOK_KEYS])
    for (const look of LOOKS) {
      const r = normalizeRecipe(withLook({}, look))
      expect(r.look).toBe(look.key)
      for (const [k, v] of Object.entries(look.set)) {
        if (k !== 'bw') expect(r[k as keyof typeof SLIDERS]).toBe(v)
      }
    }
  })

  it('keep the crop and the cut-out, and clear the other sliders', () => {
    const crop = { x: 0, y: 0, w: 0.5, h: 0.5, angle: 0, turn: 0 as const, flip_h: false, flip_v: false }
    const cutout = { points: [{ x: 0.5, y: 0.5, keep: true }], feather: 0, invert: false }
    const r = withLook({ exposure: 1, grain: 50, crop, cutout }, LOOKS.find((l) => l.key === 'mono')!)
    expect(r).toEqual({ crop, cutout, look: 'mono', bw: true, contrast: 10 })
    expect(withLook(r, null)).toEqual({ crop, cutout })
  })
})
