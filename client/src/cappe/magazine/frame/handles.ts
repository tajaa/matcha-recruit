import type { FrameTarget } from '../canvas/bridge'
import { clamp, onPlace, place, post, state, ui } from './state'
import { blockOf, storyOf } from './targets'

/** Grips over what can be dragged on the page: a selected cover element
 *  (move, widen) and the words on a photo (move), as `mz-move` in percent of
 *  their box; and the dot that sets what a cover picture keeps in view
 *  (`mz-focal`). The page moves as you drag; the editor outside is told
 *  once, when you let go. */

const grip = ui('span', 'mze-grip')
grip.title = 'Drag to move'
const width = ui('span', 'mze-grip mze-width')
width.title = 'Drag to widen'
const dot = ui('span', 'mze-focal')
dot.title = 'Drag to choose what the picture keeps in view'

type Movable = { el: HTMLElement; box: Element | null; centred: boolean }

function movable(): Movable | null {
  const { selected, selectedEl, overlay } = state
  if (!selectedEl) return null
  if (selected.kind === 'cover' && selected.el !== 'photo') {
    return { el: selectedEl as HTMLElement, box: selectedEl.closest('[data-mz-art]'), centred: false }
  }
  if (overlay && selectedEl.contains(overlay) && document.contains(overlay)) {
    return { el: overlay as HTMLElement, box: overlay.closest('.mz-frame'), centred: true }
  }
  return null
}

function focalTarget(): HTMLElement | null {
  const { selected, selectedEl } = state
  if (!selectedEl) return null
  if (selected.kind === 'cover' && selected.el === 'photo') return document.querySelector('.mz-issue__face [data-mz-focal]')
  if (selected.kind === 'block') return selectedEl.querySelector(':scope > [data-mz-focal], .mz-cover__media[data-mz-focal]')
  return null
}

const focalOf = (f: Element) => (f.getAttribute('data-mz-focal') || '50,50').split(',').map(Number)

onPlace(() => {
  const m = movable(), f = focalTarget()
  grip.style.display = width.style.display = dot.style.display = 'none'
  if (m?.box) {
    const r = m.el.getBoundingClientRect()
    Object.assign(grip.style, { display: 'block', left: `${r.left - 9}px`, top: `${r.top - 9}px` })
    if (!m.centred) Object.assign(width.style, { display: 'block', left: `${r.right - 9}px`, top: `${r.top + r.height / 2 - 9}px` })
  }
  if (f) {
    const fr = f.getBoundingClientRect(), [x, y] = focalOf(f)
    Object.assign(dot.style, { display: 'block', left: `${fr.left + fr.width * x / 100 - 11}px`, top: `${fr.top + fr.height * y / 100 - 11}px` })
  }
})

const r1 = (n: number) => Math.round(n * 10) / 10

function drag(handle: HTMLElement, onMove: (dx: number, dy: number) => void, onEnd: () => void, after: () => void) {
  handle.addEventListener('pointerdown', (e) => {
    e.preventDefault()
    handle.setPointerCapture(e.pointerId)
    const x0 = e.clientX, y0 = e.clientY
    const move = (ev: PointerEvent) => onMove(ev.clientX - x0, ev.clientY - y0)
    const up = () => {
      handle.removeEventListener('pointermove', move)
      handle.removeEventListener('pointerup', up)
      onEnd()
      after()
    }
    handle.addEventListener('pointermove', move)
    handle.addEventListener('pointerup', up)
  })
}

type Start = { x: number; y: number; w: number; box: DOMRect }
const begin = (m: Movable): Start => {
  const s = m.el.style
  return { x: parseFloat(s.left) || 0, y: parseFloat(s.top) || 0, w: parseFloat(s.width) || 0, box: m.box!.getBoundingClientRect() }
}

function moveTarget(m: Movable): FrameTarget | Record<string, unknown> {
  if (state.selected.kind === 'cover') return state.selected
  return { kind: 'overlay', story: storyOf(m.el), block: blockOf(m.el), overlay: m.el.getAttribute('data-mz-drag') }
}

export function startHandles() {
  let start: Start | null = null
  drag(grip, (dx, dy) => {
    const m = movable()
    if (!m?.box) return
    start ??= begin(m)
    const x = clamp(start.x + dx / start.box.width * 100, 0, m.centred ? 100 : 100 - (start.w || 0))
    const y = clamp(start.y + dy / start.box.height * 100, 0, 100)
    m.el.style.left = `${r1(x)}%`
    m.el.style.top = `${r1(y)}%`
    place()
  }, () => {
    const m = movable()
    if (m && start) {
      // Words on a photo are placed in whole percents (story_schema).
      const round = m.centred ? Math.round : r1
      post({ type: 'mz-move', target: moveTarget(m), x: round(parseFloat(m.el.style.left)), y: round(parseFloat(m.el.style.top)) })
    }
    start = null
  }, place)
  drag(width, (dx) => {
    const m = movable()
    if (!m?.box) return
    start ??= begin(m)
    m.el.style.width = `${r1(clamp(start.w + dx / start.box.width * 100, 10, 100 - start.x))}%`
    place()
  }, () => {
    const m = movable()
    if (m && start) post({ type: 'mz-move', target: moveTarget(m), x: start.x, y: start.y, w: r1(parseFloat(m.el.style.width)) })
    start = null
  }, place)
  let focal: { x: number; y: number; r: DOMRect } | null = null
  drag(dot, (dx, dy) => {
    const f = focalTarget()
    if (!f) return
    if (!focal) { const [x, y] = focalOf(f); focal = { x, y, r: f.getBoundingClientRect() } }
    const x = Math.round(clamp(focal.x + dx / focal.r.width * 100, 0, 100))
    const y = Math.round(clamp(focal.y + dy / focal.r.height * 100, 0, 100))
    f.setAttribute('data-mz-focal', `${x},${y}`)
    const img = f.querySelector('img')
    if (img) {
      img.style.objectPosition = `${x}% ${y}%`
      if (img.style.transformOrigin) img.style.transformOrigin = `${x}% ${y}%`
    }
    place()
  }, () => {
    const f = focalTarget()
    if (f && focal) {
      const [x, y] = focalOf(f)
      post({ type: 'mz-focal', target: state.selected, x, y })
    }
    focal = null
  }, place)
}
