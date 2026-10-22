// Loads the Studio's faces: each once, its bytes both measured (the shaper)
// and shown (a FontFace under the face's own name), so what is measured is
// what is drawn.

import { charOf, type FullChar } from '../model/doc'
import type { Doc, Face } from '../model/types'
import type { Measure } from '../compose/compose'
import { Shaper } from '../compose/shaper'
import { faceUrl, familyName, type FaceBook } from './faces'

export class FontLoader {
  private loading = new Map<string, Promise<void>>()
  readonly book: FaceBook
  readonly shaper: Shaper

  constructor(book: FaceBook, shaper: Shaper) {
    this.book = book
    this.shaper = shaper
  }

  ensure(face: Face): Promise<void> {
    let p = this.loading.get(face.sha)
    if (!p) {
      p = (async () => {
        const res = await fetch(faceUrl(face.sha))
        if (!res.ok) throw new Error(`The face ${face.family} couldn’t be loaded.`)
        const bytes = await res.arrayBuffer()
        this.shaper.add(face, bytes)
        const ff = new FontFace(familyName(face.sha), bytes)
        document.fonts.add(await ff.load())
      })()
      p.catch(() => this.loading.delete(face.sha))
      this.loading.set(face.sha, p)
    }
    return p
  }

  /** The face a run is measured in (the default when its own isn't built). */
  faceOf(c: FullChar): Face | undefined {
    return this.book.measureFace(c.font, c.wt, c.it)
  }

  /** Every face a document sets, and the default. */
  async ensureDoc(doc: Doc): Promise<void> {
    const faces = new Map<string, Face>()
    const add = (c: FullChar) => { const f = this.faceOf(c); if (f) faces.set(f.sha, f) }
    add(charOf({}))
    for (const t of doc.threads) for (const p of t.paras) for (const r of p.runs) add(charOf(r))
    await Promise.all([...faces.values()].map((f) => this.ensure(f)))
  }

  measure: Measure = {
    width: (c, text) => {
      const face = this.faceOf(c)
      return face ? this.shaper.width(face, text, c.size, c.track) : text.length * 0.5 * c.size
    },
    metrics: (c) => {
      const face = this.faceOf(c)
      return face ? Shaper.metrics(face, c.size) : { asc: 0.8 * c.size, desc: 0.2 * c.size }
    },
  }
}

let canvas: CanvasRenderingContext2D | null = null

/** Text the face lacks, measured by the browser as it will draw it. */
export function browserWidth(text: string, face: Face, size: number): number {
  canvas ??= document.createElement('canvas').getContext('2d')
  if (!canvas) return text.length * 0.5 * size
  canvas.font = `100px '${familyName(face.sha)}', sans-serif`
  return (canvas.measureText(text).width / 100) * size
}
