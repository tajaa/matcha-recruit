/** Canvas sizes and the shared frame timeline for WeekComposition. Kept out of
 *  the component file so fast refresh keeps working. */
export type Variant = 'wide' | 'narrow'
export type Layout = {
  w: number
  h: number
  pad: number
  nameW: number
  hoursW: number
  dayHeadY: number
  dayHeadH: number
  rowsY: number
  rowH: number
  bottomY: number
  /** font scale */
  s: number
  days: number[]
  barLabels: boolean
}

export const LAYOUTS: Record<Variant, Layout> = {
  wide: {
    w: 1600,
    h: 860,
    pad: 48,
    nameW: 230,
    hoursW: 124,
    dayHeadY: 124,
    dayHeadH: 82,
    rowsY: 214,
    rowH: 64,
    bottomY: 752,
    s: 1,
    days: [0, 1, 2, 3, 4, 5, 6],
    barLabels: true,
  },
  narrow: {
    w: 720,
    h: 1060,
    pad: 28,
    nameW: 150,
    hoursW: 84,
    dayHeadY: 132,
    dayHeadH: 96,
    rowsY: 240,
    rowH: 72,
    bottomY: 836,
    s: 1.3,
    days: [3, 4, 5, 6],
    barLabels: false,
  },
}

export const FPS = 30
export const DURATION = 600
/** Frame shown when motion is reduced: the finished, published week. */
export const STILL_FRAME = 560

export const T = {
  forecast: 40,
  shifts: 118,
  shiftsSpan: 170,
  check: 300,
  checkEnd: 350,
  flag: 348,
  resolve: 412,
  stamp: 494,
  fadeOut: 576,
}
