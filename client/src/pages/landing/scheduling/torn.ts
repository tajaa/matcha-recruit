/**
 * Torn-paper edges as a CSS clip-path, generated from a seed so every slip is
 * different but stable across renders. Top and bottom are hand-torn (ragged);
 * the sides are scissor cuts (nearly straight). Percentages, so it scales
 * with whatever it clips.
 */
function rng(seed: number) {
  let s = (seed * 2654435761) >>> 0 || 1
  return () => {
    s ^= s << 13
    s >>>= 0
    s ^= s >> 17
    s ^= s << 5
    s >>>= 0
    return s / 4294967296
  }
}

export function tornClip(seed: number, { tear = 7, cut = 0.8, steps = 22 }: { tear?: number; cut?: number; steps?: number } = {}): string {
  const r = rng(seed)
  const pts: string[] = []
  let drift = 0
  const ragged = () => {
    drift = drift * 0.55 + (r() - 0.5) * tear
    return Math.max(0, Math.min(tear * 1.4, tear / 2 + drift + (r() - 0.5) * tear * 0.6))
  }
  // top: left → right
  for (let i = 0; i <= steps; i++) pts.push(`${(i / steps) * 100}% ${ragged().toFixed(2)}%`)
  // right side: a couple of scissor wobbles
  pts.push(`${(100 - r() * cut).toFixed(2)}% 50%`)
  // bottom: right → left
  for (let i = steps; i >= 0; i--) pts.push(`${(i / steps) * 100}% ${(100 - ragged()).toFixed(2)}%`)
  pts.push(`${(r() * cut).toFixed(2)}% 50%`)
  return `polygon(${pts.join(', ')})`
}

/** Deterministic small rotation in degrees for a slip. */
export function slipTilt(seed: number, max = 1.8): number {
  return (rng(seed + 11)() - 0.5) * 2 * max
}
