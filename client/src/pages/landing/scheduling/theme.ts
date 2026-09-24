/**
 * Tokens for the /matcha-scheduling landing — its own surface, not the
 * NOIR home (pages/home/theme.ts) or the ivory simpler-pages.
 *
 * Designed minimalism: paper and ink in a few alphas (and the same inverted to
 * a dark gray, BOARD), hairline grids, mono labels. Colour carries meaning
 * only — matcha green for ok/sent and the one accent word per headline, amber
 * for something waiting on you (a request, a missing rate, a warm Saturday),
 * red for a problem. Don't add a colour that isn't one of those. Type: one
 * grotesk, a serif italic for the accent word, mono for labels.
 *
 * Plain hex strings because the Remotion composition renders them inline and
 * inside SVG presentation attributes.
 */
export const PAPER = '#F2F4EF' // cool paper
export const INK = '#18211B' // ballpoint, slightly green-black
export const INK_SOFT = '#5D675F' // secondary text
export const RED_PEN = '#D9432A' // conflicts
export const STAMP = '#3F6B2A' // matcha green — the sent/published state
export const AMBER = '#C9721C' // waiting on you — pending, unpriced, attention
export const CARD = '#FBFCF9' // raised card on paper

export const BODY = "'Hanken Grotesk', ui-sans-serif, system-ui, sans-serif"
/** Accent only: one italic word per headline, never a whole line. */
export const SERIF = "'Instrument Serif', 'Times New Roman', serif"
export const MONO = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace"

/** Paper tooth: fractal-noise SVG tile, multiplied over the page at low opacity. */
export const GRAIN =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0.09  0 0 0 0 0.13  0 0 0 0 0.1  0 0 0 .55 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")"

export const FONT_HREF =
  'https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600&family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;500;700&display=swap'

/** `#RRGGBB` + alpha → `rgba()`. */
export function hexA(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}

/** The hero, and the week sheet inside it: the paper tokens above inverted to
 *  a flat dark gray. The sheet uses the same PAPER as the hero, so it sits
 *  flush on the page like the Draft grid does. Green and red lifted to read. */
export const BOARD = {
  PAPER: '#161817', // hero + board
  PAPER_DEEP: '#272A28', // empty avatar / track
  CARD: '#1F2220', // raised card
  INK: '#E9EDE5', // chalk-white text and rules
  INK_SOFT: '#8B958C',
  RED_PEN: '#EF6A4C',
  STAMP: '#8FC46B',
  AMBER: '#F0A04B',
} as const
