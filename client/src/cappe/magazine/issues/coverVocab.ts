import type {
  ContentsLayout, CoverAlign, CoverBox, CoverCase, CoverCorner, CoverFilter, CoverFont, CoverScrim, CoverTone,
  CoverTracking, CoverWeight,
} from '../../types'

/** What a cover and contents may hold: the same lists and limits as
 *  server/app/cappe/services/magazine/issue_schema.py, which
 *  test_cappe_issue_schema.py reads from this file to keep them equal. Each
 *  list starts with the server's fallback. */
export const FILTERS = ['none', 'bw', 'sepia'] as const satisfies readonly CoverFilter[]
export const SCRIMS = ['none', 'top', 'bottom', 'full'] as const satisfies readonly CoverScrim[]
export const ALIGNS = ['left', 'center', 'right'] as const satisfies readonly CoverAlign[]
export const WEIGHTS = ['bold', 'regular', 'black'] as const satisfies readonly CoverWeight[]
export const CASES = ['asis', 'upper'] as const satisfies readonly CoverCase[]
export const TRACKINGS = ['normal', 'tight', 'wide'] as const satisfies readonly CoverTracking[]
export const FONTS = ['heading', 'body'] as const satisfies readonly CoverFont[]
export const BOXES = ['none', 'solid'] as const satisfies readonly CoverBox[]
export const CREDIT_CORNERS = ['br', 'bl', 'tr', 'tl'] as const satisfies readonly CoverCorner[]
export const TONES = ['light', 'dark'] as const satisfies readonly CoverTone[]
export const CONTENTS_LAYOUTS = ['list', 'grid', 'feature'] as const satisfies readonly ContentsLayout[]

export const MAX_LINES = 8
export const MAX_STORIES = 40
/** Type size, percent of the cover's width. */
export const MIN_SIZE = 1.5
export const MAX_SIZE = 30
export const MIN_WIDTH = 10
export const ZOOM_MIN = 100
export const ZOOM_MAX = 250
/** A masthead letter's width in ems at its widest (`fitMasthead`). */
export const MASTHEAD_EM = 0.72

export const LABELS = {
  filter: { none: 'Colour', bw: 'Black & white', sepia: 'Sepia' },
  scrim: { none: 'None', top: 'From the top', bottom: 'From the bottom', full: 'All over' },
  align: { left: 'Left', center: 'Centre', right: 'Right' },
  weight: { regular: 'Regular', bold: 'Bold', black: 'Heavy' },
  case: { asis: 'As typed', upper: 'CAPITALS' },
  tracking: { tight: 'Tight', normal: 'Normal', wide: 'Wide' },
  font: { heading: 'Masthead face', body: 'Text face' },
  corner: { br: 'Bottom right', bl: 'Bottom left', tr: 'Top right', tl: 'Top left' },
  tone: { light: 'Light', dark: 'Dark' },
  layout: { list: 'List', grid: 'Grid of pictures', feature: 'Feature' },
} as const
