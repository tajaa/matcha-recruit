// Where a place in a thread's text is on screen, and what place is under a
// point: read from the composed lines as the page drew them (each line marked
// `data-t` and `data-k` by the Studio), so justification and kerning are the
// browser's own. A line box is drawn at its baseline with no height, so its
// bottom edge is the baseline.

import type { Thread } from '../model/types'

export type Caret = { x: number; base: number; k: number }

export function lineEls(root: ParentNode, thread: string): Map<number, HTMLElement> {
  const out = new Map<number, HTMLElement>()
  root.querySelectorAll<HTMLElement>(`.lyt-l[data-t="${thread}"]`).forEach((el) => out.set(Number(el.dataset.k), el))
  return out
}

function textNodes(el: HTMLElement): Text[] {
  const out: Text[] = []
  const walk = (n: Node) => n.childNodes.forEach((c) => (c.nodeType === 3 ? out.push(c as Text) : walk(c)))
  walk(el)
  return out
}

/** The screen x of the place before character `i` of a line (UTF-16), or
 *  after its last character. */
export function caretX(el: HTMLElement, i: number): number {
  const nodes = textNodes(el)
  const total = nodes.reduce((a, t) => a + t.data.length, 0)
  const box = el.getBoundingClientRect()
  if (!total) {
    if (el.classList.contains('lyt-l--c')) return box.left + box.width / 2
    if (el.classList.contains('lyt-l--r')) return box.right
    return box.left
  }
  const range = document.createRange()
  let at = 0
  const end = Math.min(i, total)
  for (const t of nodes) {
    const len = t.data.length
    if (end < at + len || (end === total && at + len === total)) {
      if (end < total) {
        const j = end - at
        const step = /[\ud800-\udbff]/.test(t.data[j] ?? '') ? 2 : 1
        range.setStart(t, j)
        range.setEnd(t, Math.min(len, j + step))
        return range.getBoundingClientRect().left
      }
      const j = Math.max(0, len - (/[\udc00-\udfff]/.test(t.data[len - 1] ?? '') ? 2 : 1))
      range.setStart(t, j)
      range.setEnd(t, len)
      return range.getBoundingClientRect().right
    }
    at += len
  }
  return box.left
}

/** The place in a line nearest screen x (an offset into the line's text). */
export function offsetAtX(el: HTMLElement, x: number): number {
  const total = textNodes(el).reduce((a, t) => a + t.data.length, 0)
  let best = 0, bd = Infinity
  for (let i = 0; i <= total; i++) {
    if (i < total && /[\udc00-\udfff]/.test(el.textContent![i])) continue
    const d = Math.abs(caretX(el, i) - x)
    if (d < bd) { bd = d; best = i }
  }
  return best
}

/** The line a place sits on: the line holding it, or (in the spaces a line
 *  broke at) the line it ends. */
export function lineFor(thread: Thread, para: number, offset: number): number {
  const lines = thread.comp?.lines ?? []
  let found = -1
  for (let k = 0; k < lines.length; k++) {
    const [, p, s, e] = lines[k]
    if (p !== para) continue
    if (offset >= s && offset <= e) return k
    if (offset > e) found = k
    if (offset < s) return found === -1 ? k : found
  }
  return found
}

/** Where the caret for a place is drawn (screen x, baseline), or null when
 *  the place is overset (on no page). */
export function caretAt(root: ParentNode, thread: Thread, para: number, offset: number): Caret | null {
  const k = lineFor(thread, para, offset)
  if (k === -1) return null
  const el = lineEls(root, thread.id).get(k)
  if (!el) return null
  const [, , s, e] = thread.comp!.lines[k]
  return { x: caretX(el, Math.min(Math.max(offset, s), e) - s), base: el.getBoundingClientRect().bottom, k }
}

/** The place under a screen point in a thread: the nearest line by its
 *  baseline (on the frames under the point first), then the nearest place on it. */
export function placeAt(root: ParentNode, thread: Thread, x: number, y: number): [number, number] | null {
  const els = lineEls(root, thread.id)
  let best: { k: number; d: number } | null = null
  for (const [k, el] of els) {
    const r = el.getBoundingClientRect()
    const size = parseFloat(getComputedStyle(el.firstElementChild ?? el).fontSize) || 12
    const top = r.bottom - size * 0.9, bottom = r.bottom + size * 0.3
    const dy = y < top ? top - y : y > bottom ? y - bottom : 0
    const dx = x < r.left ? r.left - x : x > r.right ? x - r.right : 0
    const d = dy * 4 + dx
    if (!best || d < best.d) best = { k, d }
  }
  if (!best) return null
  const [, p, s] = thread.comp!.lines[best.k]
  return [p, s + offsetAtX(els.get(best.k)!, x)]
}

/** The rectangles a text selection covers, line by line (screen). */
export function selectionRects(root: ParentNode, thread: Thread, from: [number, number], to: [number, number]):
  { left: number; right: number; base: number; size: number }[] {
  const els = lineEls(root, thread.id)
  const out = []
  for (const [k, el] of els) {
    const [, p, s, e] = thread.comp!.lines[k]
    if (p < from[0] || p > to[0]) continue
    const a = p === from[0] ? Math.max(s, from[1]) : s
    const b = p === to[0] ? Math.min(e, to[1]) : e
    const wholeGap = p !== to[0] || to[1] > e
    if (b < a || (b === a && !wholeGap)) continue
    const left = caretX(el, a - s)
    const right = b > a ? caretX(el, b - s) : left
    const size = parseFloat(getComputedStyle(el.firstElementChild ?? el).fontSize) || 12
    out.push({ left, right: wholeGap && b === e ? right + size * 0.25 : right, base: el.getBoundingClientRect().bottom, size })
  }
  return out
}
