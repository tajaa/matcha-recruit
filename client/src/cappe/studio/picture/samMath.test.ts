import { describe, expect, it } from 'vitest'
import { MASK_SIZE, SAM_SIZE, bestMask, maskAlpha, pixelTensor, promptOf, samSize } from './samMath'

describe('the cut-out model’s arithmetic', () => {
  it('fits the picture to 1024 on its long side', () => {
    expect(samSize(1080, 1587)).toEqual({ w: 697, h: 1024, scale: 1024 / 1587 })
    expect(samSize(2048, 1024).w).toBe(1024)
  })

  it('normalizes pixels channel by channel and pads with zeros', () => {
    const rgba = new Uint8ClampedArray([255, 0, 128, 255, 0, 0, 0, 255])
    const t = pixelTensor(rgba, 2, 1)
    const n = SAM_SIZE * SAM_SIZE
    expect(t.length).toBe(3 * n)
    expect(t[0]).toBeCloseTo((1 - 0.485) / 0.229, 5) // red of the first pixel
    expect(t[n]).toBeCloseTo((0 - 0.456) / 0.224, 5) // its green
    expect(t[2 * n]).toBeCloseTo((128 / 255 - 0.406) / 0.225, 5) // its blue
    expect(t[1]).toBeCloseTo((0 - 0.485) / 0.229, 5)
    expect(t[SAM_SIZE]).toBe(0) // the padding below
  })

  it('puts clicks in the model’s space', () => {
    const p = promptOf([{ x: 0.5, y: 0.25, keep: true }, { x: 1, y: 1, keep: false }], 2000, 1000)
    expect(Array.from(p.coords)).toEqual([512, 128, 1024, 512])
    expect(p.labels).toEqual([1n, 0n])
  })

  it('brings the mask back to the picture’s size, kept where the logits say', () => {
    const logits = new Float32Array(MASK_SIZE * MASK_SIZE).fill(-10)
    // Keep the left half of the padded square's top 128 cells (the picture is 2:1, so it fills the top half).
    for (let y = 0; y < 128; y++) for (let x = 0; x < 128; x++) logits[y * MASK_SIZE + x] = 10
    const a = maskAlpha(logits, 200, 100)
    expect(a.length).toBe(200 * 100)
    expect(a[50 * 200 + 20]).toBe(255) // left: kept
    expect(a[50 * 200 + 180]).toBe(0) // right: cut away
    // The kept cells end at 512 of 1024: half the picture, between pixels 99 and 100.
    expect([a[50 * 200 + 99], a[50 * 200 + 100]]).toEqual([255, 0])
    // Weaker logits make a soft edge.
    const soft = maskAlpha(logits.map((v) => v / 10), 200, 100)
    expect(soft[50 * 200 + 20]).toBeGreaterThan(240)
    expect(soft[50 * 200 + 180]).toBeLessThan(10)
  })

  it('keeps the mask it is surest of', () => {
    expect(bestMask(new Float32Array([0.85, 0.97, 0.87]))).toBe(1)
    expect(bestMask([0.9])).toBe(0)
  })
})
