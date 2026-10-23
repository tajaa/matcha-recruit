// The cut-out model's arithmetic around SlimSAM (segment.worker.ts), kept pure
// so it can be tested: the picture resized to 1024 on its long side and
// padded to a square, normalized as the model was trained; a click in the
// model's 1024 space; the mask it answers (256 × 256 over that padded square)
// brought back to the picture's own size. Checked against a Python run of the
// same model on a real picture (the Campanile cut out from two clicks).

export const SAM_SIZE = 1024
export const MASK_SIZE = 256
const MEAN = [0.485, 0.456, 0.406]
const STD = [0.229, 0.224, 0.225]

/** The picture's size inside the model's square, and the scale to it. */
export function samSize(w: number, h: number): { w: number; h: number; scale: number } {
  const scale = SAM_SIZE / Math.max(w, h)
  return { w: Math.round(w * scale), h: Math.round(h * scale), scale }
}

/** RGBA pixels (`w` × `h`, at most 1024 a side) as the model's input:
 *  channels first, normalized, padded with zeros to 1024 × 1024. */
export function pixelTensor(rgba: Uint8ClampedArray | Uint8Array, w: number, h: number): Float32Array {
  const n = SAM_SIZE * SAM_SIZE
  const out = new Float32Array(3 * n)
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4, o = y * SAM_SIZE + x
      for (let c = 0; c < 3; c++) out[c * n + o] = (rgba[i + c] / 255 - MEAN[c]) / STD[c]
    }
  }
  return out
}

/** Clicks (fractions of the picture) in the model's 1024 space, and their
 *  labels (1 keep, 0 take away). */
export function promptOf(points: { x: number; y: number; keep: boolean }[], w: number, h: number) {
  const { scale } = samSize(w, h)
  return {
    coords: new Float32Array(points.flatMap((p) => [p.x * w * scale, p.y * h * scale])),
    labels: points.map((p) => (p.keep ? 1n : 0n)),
  }
}

/** The mask's logits (256 × 256 over the padded 1024 square) as one byte a
 *  pixel of the picture (`w` × `h`): sampled smoothly, with a soft edge one
 *  pixel or so wide. */
export function maskAlpha(logits: Float32Array, w: number, h: number): Uint8Array {
  const { scale } = samSize(w, h)
  const k = (SAM_SIZE / MASK_SIZE) // 1024 px per mask cell
  const out = new Uint8Array(w * h)
  const at = (x: number, y: number) => logits[Math.min(MASK_SIZE - 1, Math.max(0, y)) * MASK_SIZE + Math.min(MASK_SIZE - 1, Math.max(0, x))]
  for (let y = 0; y < h; y++) {
    const my = ((y + 0.5) * scale) / k - 0.5
    const y0 = Math.floor(my), fy = my - y0
    for (let x = 0; x < w; x++) {
      const mx = ((x + 0.5) * scale) / k - 0.5
      const x0 = Math.floor(mx), fx = mx - x0
      const v = (at(x0, y0) * (1 - fx) + at(x0 + 1, y0) * fx) * (1 - fy) + (at(x0, y0 + 1) * (1 - fx) + at(x0 + 1, y0 + 1) * fx) * fy
      out[y * w + x] = Math.round(255 / (1 + Math.exp(-4 * v)))
    }
  }
  return out
}

/** Which of the model's three masks to keep: the one it is surest of. */
export function bestMask(scores: Float32Array | number[]): number {
  let best = 0
  for (let i = 1; i < scores.length; i++) if (scores[i] > scores[best]) best = i
  return best
}
