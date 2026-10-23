// A paged story's document: the server's shape (server/app/cappe/services/
// magazine/studio/schema.py). Lengths are points; an item sits on one page,
// in that page's coordinates; text flows through threads of text frames.

import type { Recipe } from '../picture/recipe'

export type Units = 'pt' | 'pc' | 'in' | 'mm' | 'cm' | 'px'
export type Align = 'l' | 'c' | 'r' | 'j' | 'ja'
export type Role = 'p' | 'h1' | 'h2' | 'h3' | 'quote' | 'caption'
export type VAlign = 'top' | 'center' | 'bottom' | 'justify'
export type Fit = 'fill' | 'fit' | 'stretch'

/** Character attributes (stored only when not their default). */
export type CharAttrs = {
  font?: string
  wt?: number
  it?: boolean
  size?: number
  track?: number
  color?: string
  u?: boolean
}
export type Run = CharAttrs & { t: string }

/** Paragraph attributes (stored only when not their default). */
export type ParaAttrs = {
  align?: Align
  li?: number
  ri?: number
  fi?: number
  sb?: number
  sa?: number
  lead?: number
  role?: Role
}
export type Para = ParaAttrs & { runs: Run[] }

/** [frame index, para, start, end (UTF-16), x, baseline, width, align (0 l, 1 c, 2 r, 3 justified)] */
export type Line = [number, number, number, number, number, number, number, number]
export type Comp = { lines: Line[] }

export type Thread = { id: string; frames: string[]; paras: Para[]; comp?: Comp }

export type Stroke = { c: string; w: number }

type Base = {
  id: string
  page: string
  x: number
  y: number
  w: number
  h: number
  rot: number
  opacity: number
  locked: boolean
  hidden: boolean
  name: string
}
export type TextItem = Base & {
  kind: 'text'
  cols: number
  gutter: number
  inset: number
  valign: VAlign
  fill: string | null
  stroke: Stroke | null
}
export type ImageItem = Base & {
  kind: 'image'
  asset_id: string | null
  fit: Fit
  fx: number
  fy: number
  zoom: number
  fill: string | null
  stroke: Stroke | null
  radius: number
  caption: string
}
export type RectItem = Base & { kind: 'rect'; fill: string | null; stroke: Stroke | null; radius: number }
export type EllipseItem = Base & { kind: 'ellipse'; fill: string | null; stroke: Stroke | null }
export type LineItem = Base & { kind: 'line'; stroke: Stroke; flip: boolean }
export type Item = TextItem | ImageItem | RectItem | EllipseItem | LineItem
export type Kind = Item['kind']

export type Guide = { id: string; page: string; axis: 'v' | 'h'; at: number }
export type Page = { id: string }

export type Doc = {
  v: 1
  size: { w: number; h: number }
  facing: boolean
  margins: { t: number; b: number; i: number; o: number }
  cols: { n: number; g: number }
  baseline: { start: number; step: number }
  grid: { step: number }
  bleed: number
  units: Units
  paper: string
  pages: Page[]
  guides: Guide[]
  items: Item[]
  threads: Thread[]
  paywall_page: number | null
}

/** A library picture as the renderer needs it (`cappe_assets` row). */
export type Asset = {
  id: string
  url: string
  alt?: string | null
  credit_line?: string | null
  license?: string | null
  ai_generated?: boolean
  source_url?: string | null
  width?: number | null
  height?: number | null
  variants?: { webp?: { w: number; url: string }[] } | null
  /** An edited picture's source and what was done (picture/recipe.ts), to edit it again. */
  kind?: string
  parent?: string | null
  recipe?: Recipe | null
}

/** A face of the Studio's own (fonts_manifest.json). */
export type Face = {
  family: string
  weight: number
  italic: boolean
  sha: string
  bytes: number
  upm: number
  asc: number
  desc: number
  cap: number
  x: number
  features: string[]
}
