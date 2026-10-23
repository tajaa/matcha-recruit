// What the side panel adds (ui/add/AddPanel.tsx): shapes, lines, picture
// frames and colour blocks, made of the page's own kinds; and type, as single
// styles and as pairings set in one frame. Every face named here is one the
// Studio has (fonts_manifest.json; addCatalog.test.ts).

import type { CharAttrs, Doc, Kind, ParaAttrs } from '../../model/types'

export type Box = { w: number; h: number }

export type ElementSpec = {
  id: string
  label: string
  kind: Exclude<Kind, 'text'>
  /** Its size on a page of this document (ignored by a `place`). */
  size: (doc: Doc) => Box
  patch?: Record<string, unknown>
  /** Where it goes on the page, wherever it is dropped: the whole page
   *  (to the bleed), a band across the top or bottom, or a side column. */
  place?: 'page' | 'top' | 'bottom' | 'side'
  /** Behind everything else. */
  back?: boolean
}

const INK = '#1a1a1a'
const STONE = '#d9d4cc'
const BLOCK = '#ece4d6'
const fixed = (w: number, h: number) => () => ({ w, h })
const whole = (doc: Doc) => ({ w: doc.size.w, h: doc.size.h })

export const ELEMENT_GROUPS: { title: string; items: ElementSpec[] }[] = [
  {
    title: 'Shapes',
    items: [
      { id: 'square', label: 'Square', kind: 'rect', size: fixed(144, 144), patch: { fill: STONE } },
      { id: 'rounded', label: 'Rounded square', kind: 'rect', size: fixed(144, 144), patch: { fill: STONE, radius: 24 } },
      { id: 'circle', label: 'Circle', kind: 'ellipse', size: fixed(144, 144), patch: { fill: STONE } },
      { id: 'pill', label: 'Pill', kind: 'rect', size: fixed(216, 72), patch: { fill: STONE, radius: 36 } },
      { id: 'square-outline', label: 'Square outline', kind: 'rect', size: fixed(144, 144), patch: { fill: null, stroke: { c: INK, w: 2 } } },
      { id: 'circle-outline', label: 'Circle outline', kind: 'ellipse', size: fixed(144, 144), patch: { fill: null, stroke: { c: INK, w: 2 } } },
    ],
  },
  {
    title: 'Lines',
    items: [
      { id: 'hairline', label: 'Hairline', kind: 'line', size: fixed(216, 0), patch: { stroke: { c: INK, w: 0.5 } } },
      { id: 'rule', label: 'Rule', kind: 'line', size: fixed(216, 0), patch: { stroke: { c: INK, w: 1 } } },
      { id: 'thick-rule', label: 'Thick rule', kind: 'line', size: fixed(216, 0), patch: { stroke: { c: INK, w: 4 } } },
      { id: 'upright-rule', label: 'Upright rule', kind: 'line', size: fixed(0, 216), patch: { stroke: { c: INK, w: 1 } } },
    ],
  },
  {
    title: 'Picture frames',
    items: [
      { id: 'frame-landscape', label: 'Landscape 3:2', kind: 'image', size: fixed(288, 192) },
      { id: 'frame-portrait', label: 'Portrait 4:5', kind: 'image', size: fixed(192, 240) },
      { id: 'frame-square', label: 'Square', kind: 'image', size: fixed(216, 216) },
      { id: 'frame-circle', label: 'Circle', kind: 'image', size: fixed(192, 192), patch: { radius: 96 } },
      { id: 'frame-rounded', label: 'Rounded', kind: 'image', size: fixed(240, 180), patch: { radius: 16 } },
      { id: 'frame-page', label: 'Whole page', kind: 'image', size: whole, place: 'page', back: true },
    ],
  },
  {
    title: 'Colour blocks',
    items: [
      { id: 'block-page', label: 'Page colour', kind: 'rect', size: whole, place: 'page', back: true, patch: { fill: BLOCK } },
      { id: 'block-top', label: 'Top band', kind: 'rect', size: whole, place: 'top', back: true, patch: { fill: BLOCK } },
      { id: 'block-bottom', label: 'Bottom band', kind: 'rect', size: whole, place: 'bottom', back: true, patch: { fill: BLOCK } },
      { id: 'block-side', label: 'Side column', kind: 'rect', size: whole, place: 'side', back: true, patch: { fill: BLOCK } },
    ],
  },
]

export const ELEMENTS: ElementSpec[] = ELEMENT_GROUPS.flatMap((g) => g.items)

// ── type ─────────────────────────────────────────────────────────────────────

export type TextPart = { text: string; char: CharAttrs; para: ParaAttrs }
export type TextStyle = {
  id: string
  label: string
  parts: TextPart[]
  /** How wide its frame starts: the page's text area, about half of it, or a column's width. */
  width: 'content' | 'half' | 'narrow'
}

const part = (text: string, char: CharAttrs, para: ParaAttrs = {}): TextPart => ({ text, char, para })

/** One style each: Canva's "Add a heading" list. */
export const TEXT_STYLES: TextStyle[] = [
  { id: 'heading', label: 'Add a heading', width: 'content',
    parts: [part('Add a heading', { font: 'Playfair Display', wt: 800, size: 44 }, { role: 'h1', lead: 48 })] },
  { id: 'subheading', label: 'Add a subheading', width: 'content',
    parts: [part('Add a subheading', { font: 'Playfair Display', wt: 600, size: 22 }, { role: 'h2', lead: 27 })] },
  { id: 'body', label: 'Add a little bit of body text', width: 'half',
    parts: [part('Add a little bit of body text. Double-click to type your own, and link frames to let it flow on.', {}, { role: 'p' })] },
  { id: 'kicker', label: 'Kicker', width: 'half',
    parts: [part('KICKER', { font: 'Inter', wt: 700, size: 9, track: 200, color: '#b4532a' })] },
  { id: 'quote', label: 'Pull quote', width: 'content',
    parts: [part('“A line worth pulling out of the story.”', { font: 'Playfair Display', wt: 400, it: true, size: 26 },
      { role: 'quote', align: 'c', lead: 32 })] },
  { id: 'caption', label: 'Caption', width: 'narrow',
    parts: [part('A caption: what the picture shows, and why it matters.', { font: 'Inter', wt: 400, size: 8, color: '#52525b' },
      { role: 'caption', lead: 11 })] },
]

/** Pairings: a kicker, headline and dek set together in one frame. */
export const TEXT_COMBOS: TextStyle[] = [
  { id: 'editorial', label: 'Editorial', width: 'content', parts: [
    part('FEATURE', { font: 'Inter', wt: 700, size: 9, track: 200, color: '#b4532a' }),
    part('The Long Way Home', { font: 'Playfair Display', wt: 900, size: 46 }, { role: 'h1', lead: 50, sb: 6 }),
    part('A dek that pulls the reader into the story in a sentence or two.', { font: 'Source Serif 4', it: true, size: 13 },
      { lead: 18, sb: 8 }),
  ] },
  { id: 'modern', label: 'Modern', width: 'content', parts: [
    part('Design for the Way We Live', { font: 'Inter', wt: 800, size: 40, track: -20 }, { role: 'h1', lead: 44 }),
    part('Clean lines, plain words and room to breathe.', { font: 'Inter', wt: 400, size: 13, color: '#52525b' }, { lead: 18, sb: 8 }),
  ] },
  { id: 'fashion', label: 'Fashion', width: 'content', parts: [
    part('THE COLLECTIONS', { font: 'Montserrat', wt: 600, size: 9, track: 300 }, { align: 'c' }),
    part('Spring Edit', { font: 'Bodoni Moda', wt: 700, size: 58 }, { role: 'h1', align: 'c', lead: 60, sb: 6 }),
    part('Twelve looks for the season, shot on the coast.', { font: 'Montserrat', wt: 300, size: 12 }, { align: 'c', lead: 17, sb: 6 }),
  ] },
  { id: 'news', label: 'News', width: 'content', parts: [
    part('BREAKING', { font: 'Libre Franklin', wt: 800, size: 9, track: 100, color: '#c0262d' }),
    part('THE CITY VOTES TONIGHT', { font: 'Anton', wt: 400, size: 48 }, { role: 'h1', lead: 50, sb: 4 }),
    part('What is on the ballot, and what it means for your street.', { font: 'Libre Franklin', wt: 400, size: 12 },
      { lead: 17, sb: 6 }),
  ] },
  { id: 'literary', label: 'Literary', width: 'content', parts: [
    part('On Small Rooms', { font: 'EB Garamond', wt: 500, size: 42 }, { role: 'h1', align: 'c', lead: 46 }),
    part('An essay about the places we grow up in.', { font: 'EB Garamond', wt: 400, it: true, size: 15 },
      { align: 'c', lead: 20, sb: 6 }),
  ] },
  { id: 'poster', label: 'Poster', width: 'content', parts: [
    part('SUMMER NIGHTS', { font: 'Bebas Neue', wt: 400, size: 72, track: 20 }, { role: 'h1', lead: 68 }),
    part('Open-air films every Friday in August', { font: 'Oswald', wt: 400, size: 14, track: 100 }, { lead: 18, sb: 4 }),
  ] },
  { id: 'display', label: 'Display', width: 'content', parts: [
    part('Summer', { font: 'Abril Fatface', wt: 400, size: 64 }, { role: 'h1', lead: 64 }),
    part('A guide to the long, slow days.', { font: 'DM Sans', wt: 500, size: 13 }, { lead: 18, sb: 4 }),
  ] },
  { id: 'zine', label: 'Zine', width: 'content', parts: [
    part('// ISSUE 04', { font: 'IBM Plex Mono', wt: 400, size: 10 }),
    part('Making Things by Hand', { font: 'Space Grotesk', wt: 700, size: 40 }, { role: 'h1', lead: 42, sb: 4 }),
    part('Notes from a summer of workshops.', { font: 'IBM Plex Mono', wt: 400, size: 11 }, { lead: 16, sb: 6 }),
  ] },
  { id: 'notebook', label: 'Notebook', width: 'content', parts: [
    part('notes from the road', { font: 'Caveat', wt: 600, size: 36 }, { role: 'h1', lead: 38 }),
    part('Three weeks, one van and a lot of coffee.', { font: 'Lora', wt: 400, it: true, size: 12 }, { lead: 17, sb: 4 }),
  ] },
  { id: 'classic', label: 'Classic', width: 'content', parts: [
    part('A Season at the Opera', { font: 'Libre Caslon Display', wt: 400, size: 44 }, { role: 'h1', lead: 48 }),
    part('Behind the curtain with the company’s youngest singers.', { font: 'Newsreader', wt: 400, it: true, size: 14 },
      { lead: 19, sb: 6 }),
  ] },
]

/** The faces a style sets: [family, weight, italic]. */
export function facesOf(style: TextStyle, defaults: { font: string; wt: number }): [string, number, boolean][] {
  const seen = new Map<string, [string, number, boolean]>()
  for (const p of style.parts) {
    const f: [string, number, boolean] = [p.char.font ?? defaults.font, p.char.wt ?? defaults.wt, !!p.char.it]
    seen.set(f.join('|'), f)
  }
  return [...seen.values()]
}
