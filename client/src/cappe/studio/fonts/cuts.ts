// Gummfit cuts (server studio/cuts.py, held equal by a server test): faces of
// the Studio's own, built from open-licensed variable fonts fixed at a display
// optical size or a condensed or expanded width. The Studio only: the classic
// story editor sets type from Google Fonts by name, which doesn't serve them.
// A page naming one whose faces aren't built falls back to its source (or `fallback`).

import type { MagFont } from '../../magazine/design/fonts'

/** `fallback`: set by name (a catalog family) while its faces aren't built; its source when left out. */
export type Cut = MagFont & { source: string; axes: Record<string, number>; fallback?: string }

const w = (lo: number, hi: number) => Array.from({ length: (hi - lo) / 100 + 1 }, (_, k) => lo + k * 100)

export const CUTS: Cut[] = [
  { name: 'Bodoni Moda Display', cat: 'serif', body: false, w: w(400, 900), i: w(400, 900), source: 'Bodoni Moda', axes: { opsz: 96 } },
  { name: 'Fraunces Display', cat: 'serif', body: false, w: w(100, 900), i: w(100, 900), source: 'Fraunces', axes: { opsz: 144 } },
  { name: 'Playfair Poster', cat: 'serif', body: false, w: w(300, 900), i: w(300, 900), source: 'Playfair', axes: { opsz: 1200 }, fallback: 'Playfair Display' },
  { name: 'Playfair Condensed Poster', cat: 'serif', body: false, w: w(300, 900), i: w(300, 900), source: 'Playfair', axes: { opsz: 1200, wdth: 87.5 }, fallback: 'Playfair Display' },
  { name: 'Noto Serif Display Condensed', cat: 'serif', body: false, w: w(100, 900), i: w(100, 900), source: 'Noto Serif Display', axes: { wdth: 62.5 } },
  { name: 'Anybody Condensed', cat: 'display', body: false, w: w(100, 900), i: w(100, 900), source: 'Anybody', axes: { wdth: 50 } },
  { name: 'Anybody Expanded', cat: 'display', body: false, w: w(100, 900), i: w(100, 900), source: 'Anybody', axes: { wdth: 150 } },
  { name: 'Archivo Condensed', cat: 'sans', body: false, w: w(100, 900), i: w(100, 900), source: 'Archivo', axes: { wdth: 62 } },
  { name: 'Archivo Expanded', cat: 'sans', body: false, w: w(100, 900), i: w(100, 900), source: 'Archivo', axes: { wdth: 125 } },
  { name: 'League Gothic Condensed', cat: 'display', body: false, w: [400], i: [], source: 'League Gothic', axes: { wdth: 75 } },
  { name: 'Bricolage Grotesque Condensed', cat: 'display', body: false, w: w(200, 800), i: [], source: 'Bricolage Grotesque', axes: { wdth: 75 } },
]

export const CUT_BY_NAME = new Map(CUTS.map((c) => [c.name, c]))
