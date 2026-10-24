// A page's beat in the issue's rhythm (the issue board): what a reader meets
// turning to it — a picture to the edges, a portrait, a quiet detail with
// white around it, words, or a white page to breathe. Worked out from what
// covers the page, sampled on a grid, so overlapping frames count once and a
// picture hanging over from the facing page counts where it shows.

import { spreads } from './doc'
import type { Doc, Item } from './types'

export type Beat = 'bleed' | 'picture' | 'portrait' | 'pictures' | 'detail' | 'words' | 'mixed' | 'colour' | 'white'

export const BEAT_LABEL: Record<Beat, string> = {
  bleed: 'Full-bleed picture',
  picture: 'Picture',
  portrait: 'Portrait',
  pictures: 'Pictures',
  detail: 'Quiet detail',
  words: 'Words',
  mixed: 'Words and pictures',
  colour: 'Colour',
  white: 'White space',
}

/** A page's beat; and how much of it pictures, words and anything at all
 *  cover (0–1), and how heavy it looks (0 white, 1 a full-page picture). */
export type PageBeat = { beat: Beat; pictures: number; words: number; ink: number; weight: number }

const COLS = 24

type Cover = 'pic' | 'text' | 'shape'

/** What an item puts on a page, or null (lines, empty or paper-coloured
 *  shapes, text frames with no words). */
function coverOf(doc: Doc, item: Item, worded: Set<string>): Cover | null {
  if (item.hidden || item.opacity === 0) return null
  if (item.kind === 'image') return 'pic'
  if (item.kind === 'text') return worded.has(item.id) ? 'text' : item.fill && item.fill !== doc.paper ? 'shape' : null
  if (item.kind === 'graphic') return 'shape'
  if (item.kind === 'line') return null
  return item.fill && item.fill !== doc.paper ? 'shape' : null
}

/** Whether a point (page coordinates) is inside an item, turned or not. */
function inside(item: Item, x: number, y: number): boolean {
  let px = x, py = y
  if (item.rot) {
    const cx = item.x + item.w / 2, cy = item.y + item.h / 2
    const a = (-item.rot * Math.PI) / 180
    const dx = x - cx, dy = y - cy
    px = cx + dx * Math.cos(a) - dy * Math.sin(a)
    py = cy + dx * Math.sin(a) + dy * Math.cos(a)
  }
  return px >= item.x && px <= item.x + item.w && py >= item.y && py <= item.y + item.h
}

/** The text frames holding words (of their thread's composed lines). */
export function wordedFrames(doc: Doc): Set<string> {
  const out = new Set<string>()
  for (const t of doc.threads) {
    if (t.comp?.lines.length) {
      for (const l of t.comp.lines) if (l[3] > l[2]) out.add(t.frames[l[0]])
    } else if (t.paras.some((p) => p.runs.some((r) => r.t.trim()))) out.add(t.frames[0])
  }
  return out
}

/** Every page's beat, in page order. */
export function beats(doc: Doc): PageBeat[] {
  const { w, h } = doc.size
  const rows = Math.max(1, Math.round((COLS * h) / w))
  const worded = wordedFrames(doc)
  const index = new Map(doc.pages.map((p, i) => [p.id, i]))
  const byPage = doc.pages.map(() => [] as Item[])
  for (const it of doc.items) {
    const i = index.get(it.page)
    if (i !== undefined) byPage[i].push(it)
  }
  // A page's neighbours on its spread, and how far across they sit.
  const across = new Map<number, { page: number; dx: number }[]>()
  for (const pages of spreads(doc)) {
    for (const p of pages) across.set(p, pages.filter((q) => q !== p).map((q) => ({ page: q, dx: (q - p) * w })))
  }
  return doc.pages.map((_, i) => {
    // This page's items over the neighbours' hanging across (a later page
    // is drawn over an earlier one); within a page, later items are on top.
    const layers: { item: Item; dx: number; cover: Cover }[] = []
    const add = (items: Item[], dx: number) => {
      for (const item of items) {
        const cover = coverOf(doc, item, worded)
        if (cover) layers.push({ item, dx, cover })
      }
    }
    for (const n of across.get(i) ?? []) if (n.page < i) add(byPage[n.page], n.dx)
    add(byPage[i], 0)
    for (const n of across.get(i) ?? []) if (n.page > i) add(byPage[n.page], n.dx)
    let pic = 0, text = 0, shape = 0
    const picArea = new Map<string, number>()
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < COLS; c++) {
        const x = ((c + 0.5) / COLS) * w, y = ((r + 0.5) / rows) * h
        for (let k = layers.length - 1; k >= 0; k--) {
          const { item, dx, cover } = layers[k]
          if (!inside(item, x - dx, y)) continue
          if (cover === 'pic') { pic++; picArea.set(item.id, (picArea.get(item.id) ?? 0) + 1) } else if (cover === 'text') text++
          else shape++
          break
        }
      }
    }
    const cells = rows * COLS
    const pictures = pic / cells, words = text / cells, ink = (pic + text + shape) / cells
    const weight = Math.min(1, pictures + 0.6 * (shape / cells) + 0.3 * words)
    const big = [...picArea.entries()].filter(([, n]) => n / cells >= 0.08)
    let beat: Beat
    if (pictures >= 0.85) beat = 'bleed'
    else if (pictures >= 0.2 && big.length >= 2 && words < 0.2) beat = 'pictures'
    else if (pictures >= 0.35) {
      const main = layers.find((l) => l.item.id === big[0]?.[0])?.item
      beat = words >= 0.2 && pictures < 0.6 ? 'mixed' : main && main.h >= main.w * 1.2 ? 'portrait' : 'picture'
    } else if (pictures >= 0.01) beat = words < 0.15 ? 'detail' : 'mixed'
    else if (ink < 0.04) beat = 'white'
    else if (words >= 0.12) beat = 'words'
    else if (shape / cells >= 0.5) beat = 'colour'
    else beat = ink < 0.12 ? 'white' : 'mixed'
    return { beat, pictures, words, ink, weight }
  })
}
