import type { Device } from './bridge'

/** The phone a page is checked on: a common iPhone's screen, in CSS pixels. */
export const PHONE = { width: 390, height: 844 }
/** The narrowest window the book shows two pages in, with room to spare
 *  (magazine.css: two columns from 960px). */
export const SPREAD_MIN = 1024
const BEZEL = 6

/** Where the page sits in a pane `w` × `h`, and at what scale: the reader's
 *  own layout, made smaller when the pane is narrower than a reader's
 *  window, never larger. Null before the pane is measured. */
export function fitFrame(device: Device, w: number, h: number) {
  if (!w || !h) return null
  if (device === 'phone') {
    const outer = { width: PHONE.width + 2 * BEZEL, height: PHONE.height + 2 * BEZEL }
    const scale = Math.min(1, (w - 32) / outer.width, (h - 32) / outer.height)
    return { width: PHONE.width, height: PHONE.height, scale, left: (w - outer.width * scale) / 2, top: 16, bezel: BEZEL }
  }
  const width = Math.max(w, SPREAD_MIN)
  const scale = w / width
  return { width, height: h / scale, scale, left: 0, top: 0, bezel: 0 }
}
