// How wide text is, measured as the browser will set it: HarfBuzz shaping the
// same font bytes the page loads (kerning, ligatures), one run at a time as the
// page has one span per run. CSS letter-spacing adds after every character,
// the last too, so tracking does here.
//
// A character the face doesn't have (pasted Japanese, say) is drawn by the
// browser in some other font, so text holding one is measured by the browser
// itself (`fallback`, a canvas in the Studio), not by HarfBuzz's empty glyph.

import type { Face } from '../model/types'

type HB = typeof import('harfbuzzjs')
type Loaded = { font: InstanceType<HB['Font']>; upm: number; cmap: Set<number> }

let hbLoading: Promise<HB> | null = null
export const loadHarfBuzz = (): Promise<HB> => (hbLoading ??= import('harfbuzzjs'))

/** Measures `text` in a face the shaper doesn't cover, in pt. */
export type Fallback = (text: string, face: Face, size: number) => number

const graphemes = (text: string) => [...text].length

export class Shaper {
  private fonts = new Map<string, Loaded>()
  private cache = new Map<string, number>()
  private hb: HB
  private fallback?: Fallback

  constructor(hb: HB, fallback?: Fallback) {
    this.hb = hb
    this.fallback = fallback
  }

  add(face: Face, bytes: ArrayBuffer): void {
    if (this.fonts.has(face.sha)) return
    const hbFace = new this.hb.Face(new this.hb.Blob(bytes), 0)
    const font = new this.hb.Font(hbFace)
    font.setScale(hbFace.upem, hbFace.upem)
    this.fonts.set(face.sha, { font, upm: hbFace.upem, cmap: new Set(hbFace.collectUnicodes()) })
  }

  has(sha: string): boolean {
    return this.fonts.has(sha)
  }

  /** Whether the face has every character of `text`. */
  covers(sha: string, text: string): boolean {
    const f = this.fonts.get(sha)
    if (!f) return false
    for (const ch of text) {
      const cp = ch.codePointAt(0)!
      if (cp > 0x20 && !f.cmap.has(cp) && cp !== 0xa0) return false
    }
    return true
  }

  /** The advance of `text` in ems of its face. */
  em(sha: string, text: string): number {
    const key = `${sha}|${text}`
    let em = this.cache.get(key)
    if (em === undefined) {
      const f = this.fonts.get(sha)
      if (!f) return text.length * 0.5
      const buf = new this.hb.Buffer()
      buf.addText(text)
      buf.guessSegmentProperties()
      this.hb.shape(f.font, buf)
      let units = 0
      for (const p of buf.getGlyphPositions()) units += p.xAdvance
      em = units / f.upm
      if (this.cache.size > 200_000) this.cache.clear()
      this.cache.set(key, em)
    }
    return em
  }

  /** The width of `text` set in `face` at `size` pt with `track` (thousandths
   *  of an em), in pt. */
  width(face: Face, text: string, size: number, track = 0): number {
    if (!text) return 0
    const tracking = graphemes(text) * (track / 1000) * size
    if (this.fallback && !this.covers(face.sha, text)) return this.fallback(text, face, size) + tracking
    return this.em(face.sha, text) * size + tracking
  }

  /** The face's ascent and descent at `size`, in pt (descent positive). */
  static metrics(face: Face, size: number): { asc: number; desc: number } {
    return { asc: (face.asc / face.upm) * size, desc: (-face.desc / face.upm) * size }
  }
}
