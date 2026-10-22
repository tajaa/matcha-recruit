import type { RtDoc } from '../canvas/rt'

/** A design: words, shapes and pictures laid over a picture or a page, as
 *  the server keeps it (services/magazine/design_schema.py). Every layer is
 *  placed in percent of its artboard (`x`/`w` of the width, `y`/`h` of the
 *  height); type, strokes, corners, shadows and padding are in percent of the
 *  artboard's width. Layers stack in order, the first at the bottom. */

export type Colour = string // '#rrggbb', '#rrggbbaa' or 'accent'

export type PaintKind = 'none' | 'solid' | 'linear' | 'radial'
export type Stop = { color: Colour; at: number }
export type Paint = { kind: PaintKind; color: Colour; angle: number; stops: Stop[] }

export type StrokeStyle = 'solid' | 'dashed' | 'dotted'
export type Stroke = { color: Colour; width: number; style: StrokeStyle }

export type Shadow = { inner: boolean; x: number; y: number; blur: number; spread: number; color: Colour }

export type Blend =
  | 'normal' | 'multiply' | 'screen' | 'overlay' | 'darken' | 'lighten' | 'color-dodge' | 'color-burn' | 'hard-light'
  | 'soft-light' | 'difference' | 'exclusion' | 'hue' | 'saturation' | 'color' | 'luminosity'

type Base = {
  id: string; name: string
  x: number; y: number; w: number; h: number
  rot: number; flip_x: boolean; flip_y: boolean
  opacity: number; blend: Blend; hidden: boolean; locked: boolean; link: string
}

type Painted = { fill: Paint; stroke: Stroke; radius: [number, number, number, number]; shadows: Shadow[]; blur: number }

export type TextAlign = 'left' | 'center' | 'right' | 'justify'
export type VAlign = 'top' | 'middle' | 'bottom'
export type TextCase = 'none' | 'upper' | 'lower' | 'title'

export type TextLayer = Base & Painted & {
  kind: 'text'; rt: RtDoc
  /** A face from fonts.ts, or the magazine's own: 'heading' / 'body'. */
  font: string; size: number; weight: number; italic: boolean; color: Colour
  align: TextAlign; valign: VAlign; leading: number; tracking: number; case: TextCase; pad: number
  /** 'height': the box grows with its words; 'none': a fixed box. */
  autosize: 'height' | 'none'
}

export type ImageLayer = Base & Painted & {
  kind: 'image'; asset_id: string; fit: 'cover' | 'contain'; focal: { x: number; y: number }; zoom: number
  filter: 'none' | 'bw' | 'sepia'
}

export type ShapeKind = 'rect' | 'ellipse' | 'line'
export type ShapeLayer = Base & Painted & { kind: 'shape'; shape: ShapeKind }

export type GroupLayer = Base & { kind: 'group'; children: Layer[] }

export type Layer = TextLayer | ImageLayer | ShapeLayer | GroupLayer
export type PaintedLayer = TextLayer | ImageLayer | ShapeLayer

export type Design = { layers: Layer[]; background?: Paint }

/** A designed page's shape, width over height. */
export const PAGE_ASPECTS = { '3:4': 0.75, '4:5': 0.8, '2:3': 0.6667, '1:1': 1 } as const
export type PageAspect = keyof typeof PAGE_ASPECTS

export const BLENDS: Blend[] = ['normal', 'multiply', 'screen', 'overlay', 'darken', 'lighten', 'color-dodge', 'color-burn',
  'hard-light', 'soft-light', 'difference', 'exclusion', 'hue', 'saturation', 'color', 'luminosity']

/** The limits the server keeps a design to (design_schema.py). */
export const MAX_LAYERS = 200
export const MAX_STOPS = 8
export const MAX_SHADOWS = 4
export const MAX_TEXT = 2_000
