/**
 * Tokens for the /matcha-scheduling landing — its own surface, not the
 * NOIR home (pages/home/theme.ts) or the ivory simpler-pages.
 *
 * The page is built from the back-office wall schedule: graph-paper sheet,
 * ballpoint ink, a manager's highlighter over each shift, red pen for the
 * problems, matcha green once the week goes out. Every colour below is one of
 * those instruments; don't add one that isn't. The page around the sheet stays
 * quiet: one grotesk for headlines, a serif italic for the single accent word.
 *
 * Plain hex strings because the Remotion composition renders them inline and
 * inside SVG presentation attributes.
 */
export const PAPER = '#F2F4EF' // cool graph-paper sheet
export const PAPER_DEEP = '#E6EAE2' // shaded cell / card on paper
export const GRID = '#C4D2DC' // graph-paper rule (blue, like the real pads)
export const INK = '#18211B' // ballpoint, slightly green-black
export const INK_SOFT = '#5D675F' // secondary text
export const HILITE = '#E4EE3F' // highlighter — the shift itself
export const RED_PEN = '#D9432A' // conflicts
export const STAMP = '#3F6B2A' // matcha green — the sent/published state
export const CARD = '#FBFCF9' // index card pinned to the sheet
export const TAPE = '#E6DDBF' // masking tape holding the schedule to the wall

// Static cuts only: Big Shoulders (variable) showed overlap seams inside N/W/M at
// hero sizes. Saira Extra Condensed ships static, clean at any size.
export const DISPLAY = "'Saira Extra Condensed', 'Arial Narrow', sans-serif"
export const BODY = "'Hanken Grotesk', ui-sans-serif, system-ui, sans-serif"
/** Accent only: one italic word per headline, never a whole line. */
export const SERIF = "'Instrument Serif', 'Times New Roman', serif"
export const MONO = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace"

/** Paper tooth: fractal-noise SVG tile, multiplied over the page at low opacity. */
export const GRAIN =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0.09  0 0 0 0 0.13  0 0 0 0 0.1  0 0 0 .55 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")"

export const FONT_HREF =
  'https://fonts.googleapis.com/css2?family=Saira+Extra+Condensed:wght@600;700;800&family=Hanken+Grotesk:wght@400;500;600&family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;500;700&display=swap'

/** Graph-paper background style; `cell` is the minor square in px, with a
 *  heavier rule every fifth line like a real engineering pad. */
export function graphPaper(cell: number, alpha = 0.55): { backgroundImage: string; backgroundSize: string } {
  const minor = hexA(GRID, alpha * 0.55)
  const major = hexA(GRID, alpha)
  const big = `${cell * 5}px ${cell * 5}px`
  const small = `${cell}px ${cell}px`
  return {
    backgroundImage: [
      `linear-gradient(${major} 1px, transparent 1px)`,
      `linear-gradient(90deg, ${major} 1px, transparent 1px)`,
      `linear-gradient(${minor} 1px, transparent 1px)`,
      `linear-gradient(90deg, ${minor} 1px, transparent 1px)`,
    ].join(', '),
    backgroundSize: [big, big, small, small].join(', '),
  }
}

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
} as const
