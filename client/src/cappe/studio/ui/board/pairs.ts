// Paired-picture layouts for a spread (the issue board): two facing pages
// designed together. Their frames are empty; fill one with a picture (drop
// one on it, or click a photo with it selected). In the linked layouts both
// frames show that one picture (model/crops.ts), across the spine or either
// side of it. On a blank spread a layout lays out that spread; otherwise it
// comes in as a new spread after it, so nothing is covered.

import { allIds, newId, newItem, spreads } from '../../model/doc'
import { SPINE_CLEAR } from '../../model/gutter'
import { LIMITS, docProblem, round } from '../../model/limits'
import { addPages, deleteItems } from '../../model/ops'
import type { Doc, ImageItem } from '../../model/types'
import { blankPage } from '../add/applyTemplate'

type Box = { x: number; y: number; w: number; h: number }
/** A frame on the left (0) or right (1) page; `link`: frames with the same
 *  number show one picture. */
type Slot = { side: 0 | 1; box: Box; name: string; link?: number }

export type Pair = { id: string; label: string; hint: string; slots: (d: Doc) => Slot[] }

const bleedBox = (d: Doc, side: 0 | 1, spine = 0): Box => ({
  x: side === 0 ? -d.bleed : spine, y: -d.bleed, w: d.size.w + d.bleed - spine, h: d.size.h + 2 * d.bleed,
})

/** The page's text area (inside its margins; the inside margin by the spine). */
const area = (d: Doc, side: 0 | 1): Box => {
  const m = d.margins
  const left = side === 0 ? m.o : m.i
  return { x: left, y: m.t, w: d.size.w - m.i - m.o, h: d.size.h - m.t - m.b }
}

/** A box `w` wide and `w / ratio` high, inside `a`: its bottom at `low` of
 *  the way down the room left (0 top, 1 bottom), centred across. */
const sized = (a: Box, w: number, ratio: number, low = 0.5): Box => {
  const width = Math.min(a.w, w), height = Math.min(a.h, width / ratio)
  return { x: a.x + (a.w - width) / 2, y: a.y + (a.h - height) * low, w: width, h: height }
}

export const PAIRS: Pair[] = [
  {
    id: 'across', label: 'Across the spread', hint: 'One picture over both pages, out to the edges.',
    slots: (d) => [0, 1].map((side) => ({ side: side as 0 | 1, box: bleedBox(d, side as 0 | 1), name: 'Spread picture', link: 1 })),
  },
  {
    id: 'spine', label: 'Clear of the spine', hint: 'One picture in two windows, with the fold left white.',
    slots: (d) => [0, 1].map((side) => {
      const a = area(d, side as 0 | 1)
      const inner = side === 0 ? { x: a.x, w: d.size.w - SPINE_CLEAR - a.x } : { x: SPINE_CLEAR, w: a.x + a.w - SPINE_CLEAR }
      return { side: side as 0 | 1, box: { ...a, ...inner }, name: 'Split picture', link: 1 }
    }),
  },
  {
    id: 'diptych', label: 'Diptych', hint: 'Two pictures, one on each page, matched in size and height.',
    slots: (d) => [0, 1].map((side) => ({ side: side as 0 | 1, box: sized(area(d, side as 0 | 1), area(d, 0).w * 0.82, 4 / 5, 0.45),
      name: side === 0 ? 'Left picture' : 'Right picture' })),
  },
  {
    id: 'quiet', label: 'Full bleed and a quiet page', hint: 'A dramatic picture, then a small one with white around it.',
    slots: (d) => [
      { side: 0, box: bleedBox(d, 0), name: 'Opening picture' },
      { side: 1, box: sized(area(d, 1), area(d, 1).w * 0.42, 4 / 5, 0.72), name: 'Detail' },
    ],
  },
  {
    id: 'portrait', label: 'Portrait and detail', hint: 'A tall portrait facing a small square detail.',
    slots: (d) => {
      const right = area(d, 1)
      const side = Math.min(right.w * 0.38, right.h * 0.3)
      return [
        { side: 0, box: area(d, 0), name: 'Portrait' },
        { side: 1, box: { x: right.x + right.w - side, y: right.y + right.h - side, w: side, h: side }, name: 'Detail' },
      ]
    },
  },
]

/** Where a layout would go for the spread whose pages are `pages`: that
 *  spread when both pages are blank, else a new spread after it. null when
 *  `pages` isn't two facing pages. */
export function pairTarget(doc: Doc, pages: number[]): { left: number; fresh: boolean } | null {
  const pair = spreads(doc).find((s) => s.length === 2 && s[0] === Math.min(...pages) && pages.every((p) => s.includes(p)))
  if (!pair || pages.length !== 2) return null
  return { left: pair[0], fresh: !(blankPage(doc, pair[0]) && blankPage(doc, pair[1])) }
}

/** The spread laid out (or a new spread after it). Returns the left page's
 *  index, or a reason it can't be. */
export function applyPair(doc: Doc, pages: number[], pair: Pair): { doc: Doc; left: number } | { problem: string } {
  const target = pairTarget(doc, pages)
  if (!target) return { problem: 'Pick a spread of two facing pages.' }
  if (target.fresh && doc.pages.length + 2 > LIMITS.MAX_PAGES) {
    return { problem: `A story holds at most ${LIMITS.MAX_PAGES} pages, so there’s no room for a new spread.` }
  }
  let next = doc
  let left = target.left
  if (target.fresh) {
    next = addPages(next, left + 1, 2)
    left += 2
  } else {
    const ids = new Set([next.pages[left].id, next.pages[left + 1].id])
    next = deleteItems(next, next.items.filter((i) => ids.has(i.page)).map((i) => i.id))
  }
  const taken = allIds(next)
  const links = next.items.flatMap((i) => (i.kind === 'image' && i.link ? [i.link] : []))
  const linkIds = new Map<number, string>()
  const items = pair.slots(next).map((slot) => {
    const id = newId('i', taken)
    taken.push(id)
    const box = { x: round(slot.box.x), y: round(slot.box.y), w: round(slot.box.w), h: round(slot.box.h) }
    const item = { ...newItem('image', next.pages[left + slot.side].id, id, box), name: slot.name } as ImageItem
    if (slot.link !== undefined) {
      if (!linkIds.has(slot.link)) { const l = newId('lk', links); links.push(l); linkIds.set(slot.link, l) }
      item.link = linkIds.get(slot.link)
    }
    return item
  })
  next = { ...next, items: [...next.items, ...items] }
  const problem = docProblem(next)
  return problem ? { problem } : { doc: next, left }
}
