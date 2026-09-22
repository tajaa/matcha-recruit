/**
 * Tokens for the /matcha-scheduling landing — its own surface, not the
 * NOIR home (pages/home/theme.ts) or the ivory simpler-pages.
 *
 * The page is built from the back-office wall schedule: graph-paper sheet,
 * ballpoint ink, a manager's highlighter over each shift, red pen for the
 * problems, a green rubber stamp when the week goes out. Every colour below is
 * one of those instruments; don't add one that isn't.
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
export const STAMP = '#3F6B2A' // matcha rubber stamp — the published state

export const DISPLAY = "'Big Shoulders Display', 'Arial Narrow', sans-serif"
export const BODY = "'Hanken Grotesk', ui-sans-serif, system-ui, sans-serif"
export const MONO = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace"

export const FONT_HREF =
  'https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@600;800;900&family=Hanken+Grotesk:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap'

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
