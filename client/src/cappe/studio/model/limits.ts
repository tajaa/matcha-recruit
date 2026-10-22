// How big a paged story can get, and the defaults its sparse JSON leaves out:
// the server's numbers (server/app/cappe/services/magazine/studio/limits.py),
// held equal by server/tests/cappe/test_cappe_studio_limits.py.

export const LIMITS = {
  MAX_DOC_BYTES: 4_000_000,
  MAX_PAGES: 256,
  MAX_ITEMS_PER_PAGE: 400,
  MAX_ITEMS: 6_000,
  MAX_THREADS: 200,
  MAX_THREAD_CHARS: 100_000,
  MAX_DOC_CHARS: 300_000,
  MAX_PARAS: 10_000,
  MAX_RUNS: 1_000,
  MAX_LINES: 30_000,
  MAX_GUIDES: 1_000,
  MAX_NAME: 60,
  MAX_CAPTION: 500,
  PAGE_MIN: 72,
  PAGE_MAX: 1728,
  COORD: 20_000,
  SIZE_MAX: 1296,
  TRACK_MIN: -500,
  TRACK_MAX: 2000,
  INDENT_MAX: 1000,
  LEAD_MAX: 2000,
  GUTTER_MAX: 288,
  STROKE_MAX: 144,
  RADIUS_MAX: 1000,
  ZOOM_MIN: 100,
  ZOOM_MAX: 1000,
  UNITS: ['pt', 'pc', 'in', 'mm', 'cm', 'px'],
  KINDS: ['text', 'image', 'rect', 'ellipse', 'line'],
  ALIGNS: ['l', 'c', 'r', 'j', 'ja'],
  ROLES: ['p', 'h1', 'h2', 'h3', 'quote', 'caption'],
  VALIGNS: ['top', 'center', 'bottom', 'justify'],
  FITS: ['fill', 'fit', 'stretch'],
  CHAR_DEFAULTS: { font: 'Source Serif 4', wt: 400, it: false, size: 10.5, track: 0, color: '#1a1a1a', u: false },
  PARA_DEFAULTS: { align: 'l', li: 0, ri: 0, fi: 0, sb: 0, sa: 0, lead: 0, role: 'p' },
} as const

export const CHAR_DEFAULTS = LIMITS.CHAR_DEFAULTS
export const PARA_DEFAULTS = LIMITS.PARA_DEFAULTS

/** A number rounded half up to `places` decimals, as the server rounds it. */
export function round(n: number, places = 2): number {
  const k = 10 ** places
  const v = Math.floor(n * k + 0.5) / k
  return v === 0 ? 0 : v
}

export function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n))
}
