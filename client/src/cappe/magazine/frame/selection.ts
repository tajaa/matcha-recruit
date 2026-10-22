import type { FrameTarget } from '../canvas/bridge'
import { book, onPlace, place, state, ui } from './state'
import { outlined } from './targets'

/** What is selected, and the outlines over it and over what the pointer is
 *  on. Outlines are boxes drawn over the page from an element's own pieces
 *  on screen: a paragraph running on into the next column gets a box in
 *  each, and the empty sliver a column break can leave gets none (a CSS
 *  outline would draw it). */

type Kind = 'sel' | 'hov'
const boxes: Record<Kind, HTMLElement[]> = { sel: [], hov: [] }

function draw(kind: Kind, el: Element | null) {
  const list = boxes[kind]
  const rects: [number, number, number, number][] = []
  if (el && document.contains(el)) {
    const clip = el.closest('.mz-book')?.getBoundingClientRect()
    for (const r of Array.from(el.getClientRects())) {
      let l = r.left - 3, rt = r.right + 3
      if (clip) { l = Math.max(l, clip.left); rt = Math.min(rt, clip.right) }
      if (r.height > 4 && rt - l > 8) rects.push([l, r.top - 3, rt - l, r.height + 6])
    }
  }
  while (list.length < rects.length) list.push(ui('div', `mze-box mze-box--${kind}`))
  list.forEach((d, i) => {
    const b = rects[i]
    d.style.display = b ? 'block' : 'none'
    if (b) Object.assign(d.style, { left: `${b[0]}px`, top: `${b[1]}px`, width: `${b[2]}px`, height: `${b[3]}px` })
  })
}

onPlace(() => {
  const sel = outlined(state.selected) ? state.selectedEl : null
  draw('sel', sel)
  draw('hov', state.hovered && state.hovered !== sel ? state.hovered : null)
})

/** Select `t` (its element `el`), turning the book to it when asked:
 *  `now` at once (after a reload), `smooth` as a reader would. */
export function select(t: FrameTarget, el: Element | null, turn?: 'now' | 'smooth' | null) {
  state.selectedEl?.classList.remove('mze-sel')
  state.selected = t
  state.selectedEl = el
  if (el && outlined(t)) el.classList.add('mze-sel')
  const mz = book()
  if (el && turn && mz) mz.go(mz.spreadOf(el), turn === 'now')
  place()
}
