import { onPlace, place, post, state, ui } from './state'
import { storyOf } from './targets'

/** "+" under the block the pointer is on: a menu of blocks to add after it. */

const INSERTABLE: [string, string][] = [['text', 'Text'], ['photo', 'Photo'], ['photos', 'Photos'], ['quote', 'Quote'],
  ['sidebar', 'Sidebar'], ['qa', 'Q&A'], ['divider', 'Divider']]

const plus = ui('button', 'mze-plus')
plus.type = 'button'
plus.textContent = '+'
plus.setAttribute('aria-label', 'Add a block here')
const menu = ui('div', 'mze-menu')
menu.setAttribute('role', 'menu')

let under: Element | null = null
let menuFor: Element | null = null
let hide: ReturnType<typeof setTimeout> | undefined

function placePlus(block: Element) {
  const rects = block.getClientRects(), r = rects[rects.length - 1]
  if (!r) return
  // In the gap under the block, clear of its last line.
  plus.style.display = 'block'
  plus.style.left = `${r.left + r.width / 2 - 11}px`
  plus.style.top = `${r.bottom + 2}px`
}

export function startPlus() {
  document.addEventListener('mouseover', (e) => {
    const t = e.target instanceof Element ? e.target : null
    if (!t || t.closest('.mze-ui')) { clearTimeout(hide); return }
    const b = t.closest('[data-mz-s] [data-mz-b]')
    if (b !== state.hovered) { state.hovered = b; place() }
    clearTimeout(hide)
    if (!b) { hide = setTimeout(() => { plus.style.display = 'none' }, 400); return }
    under = b
    placePlus(b)
  })
  plus.addEventListener('click', () => {
    if (!under) return
    const r = plus.getBoundingClientRect()
    menu.replaceChildren(...INSERTABLE.map(([type, label]) => {
      const b = document.createElement('button')
      b.type = 'button'
      b.setAttribute('role', 'menuitem')
      b.dataset.type = type
      b.textContent = label
      return b
    }))
    menu.style.display = 'grid'
    menu.style.left = `${Math.min(innerWidth - 180, r.left)}px`
    menu.style.top = `${Math.max(4, Math.min(innerHeight - menu.offsetHeight - 4, r.bottom + 4))}px`
    menuFor = under
  })
  menu.addEventListener('click', (e) => {
    const b = e.target instanceof Element ? e.target.closest<HTMLElement>('button') : null
    menu.style.display = 'none'
    if (!b || !menuFor) return
    post({ type: 'mz-insert', story: storyOf(menuFor), at: Number(menuFor.getAttribute('data-mz-b')) + 1, kind: b.dataset.type })
  })
  document.addEventListener('mousedown', (e) => {
    if (!(e.target instanceof Element) || !e.target.closest('.mze-menu, .mze-plus')) menu.style.display = 'none'
  })
  onPlace(() => { if (plus.style.display === 'block' && under) placePlus(under) })
}
