// The Picture Editor's looks: each is a starting set of sliders. Choosing one
// sets those sliders (and clears the rest), keeping the crop and the cut-out;
// the sliders can then be moved on from there.

import type { LookKey, Recipe, Slider } from './recipe'

export type Look = { key: LookKey; label: string; set: Partial<Record<Slider, number>> & { bw?: boolean } }

export const LOOKS: Look[] = [
  { key: 'vivid', label: 'Vivid', set: { contrast: 20, vibrance: 35, saturation: 10, clarity: 15 } },
  { key: 'warm', label: 'Warm', set: { temp: 30, tint: 5, vibrance: 10 } },
  { key: 'cool', label: 'Cool', set: { temp: -30, tint: -5, vibrance: 5 } },
  { key: 'golden', label: 'Golden hour', set: { temp: 40, tint: 8, highlights: -20, shadows: 20, hi_hue: 40, hi_amt: 25, vignette: -20 } },
  { key: 'teal', label: 'Teal & orange', set: { contrast: 15, saturation: 10, sh_hue: 190, sh_amt: 35, hi_hue: 30, hi_amt: 30 } },
  { key: 'matte', label: 'Matte', set: { fade: 35, contrast: -10, shadows: 20, saturation: -10 } },
  { key: 'film', label: 'Film', set: { fade: 20, grain: 35, contrast: 10, temp: 8, vibrance: -10 } },
  { key: 'chrome', label: 'Chrome', set: { contrast: 25, saturation: 20, highlights: -30, clarity: 20 } },
  { key: 'faded', label: 'Faded', set: { fade: 45, saturation: -30, contrast: -15 } },
  { key: 'noir', label: 'Noir', set: { bw: true, contrast: 45, blacks: -30, vignette: -35, grain: 25 } },
  { key: 'mono', label: 'Mono', set: { bw: true, contrast: 10 } },
  { key: 'sepia', label: 'Sepia', set: { bw: true, hi_hue: 35, hi_amt: 45, sh_hue: 30, sh_amt: 35 } },
  { key: 'dusk', label: 'Dusk', set: { exposure: -0.3, temp: -15, tint: 20, sh_hue: 250, sh_amt: 30 } },
]

/** The recipe with `look` chosen (null: back to no look), its crop and cut-out kept. */
export function withLook(recipe: Recipe, look: Look | null): Recipe {
  const kept: Recipe = {}
  if (recipe.crop) kept.crop = recipe.crop
  if (recipe.cutout) kept.cutout = recipe.cutout
  return look ? { ...kept, look: look.key, ...look.set } : kept
}
