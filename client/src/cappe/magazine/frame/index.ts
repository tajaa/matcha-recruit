import type { FrameTarget } from '../canvas/bridge'
import { startHandles } from './handles'
import { startPlus } from './plus'
import { select } from './selection'
import { book, place, post, state } from './state'
import { blockOf, elFor, storyOf, targetOf } from './targets'
import { followCaret, startTyping, typedRecently } from './typing'

/** The owner's editor on a magazine page (an edit render: services/magazine,
 *  `edit=True`). EditFrame writes this into the page (vite-mz-frame.ts
 *  bundles it), which runs in a frame sandboxed with scripts but without
 *  our origin, so it can't reach the dashboard or its session: it talks to
 *  the editor outside only by postMessage, and the editor checks everything
 *  it is sent (canvas/bridge.ts).
 *
 *  Words are typed straight into the page (typing.ts). A click selects what
 *  it lands on (`mz-select`): a block of a story, a cover element, the
 *  contents. Grips drag a cover element or words on a photo, a dot moves a
 *  cover photo's focus (handles.ts), a "+" under a block adds one after it
 *  (plus.ts). The book is the reader's own (book.js); `mz-goto` turns it
 *  back to the place being edited after the editor re-renders the page. */

const reader = document.querySelector('[data-mz-edit]')
if (reader) {
  startTyping()
  startPlus()
  startHandles()

  document.addEventListener('click', (e) => {
    const t = e.target
    if (!(t instanceof Element) || t.closest('.mze-ui')) return
    // Links, contents entries and cover lines don't take you anywhere here.
    if (t.closest('a, label')) { e.preventDefault(); e.stopPropagation() }
    if (t.closest('.mz-turn')) return
    const target = targetOf(t)
    state.overlay = t.closest('[data-mz-drag]')
    select(target, elFor(target))
    post({ type: 'mz-select', target })
    const pick = t.closest('[data-mz-pick]')
    if (pick) {
      const item = pick.getAttribute('data-mz-item')
      post({ type: 'mz-pick', story: storyOf(pick), block: blockOf(pick), item: item === null ? null : Number(item) })
    }
  }, true)

  const pages = reader.querySelector('.mz-book')
  let settle: ReturnType<typeof setTimeout> | undefined
  let typed: ReturnType<typeof setTimeout> | undefined
  pages?.addEventListener('scroll', () => {
    place()
    if (state.editing && typedRecently()) { clearTimeout(typed); typed = setTimeout(followCaret, 60) }
    clearTimeout(settle)
    settle = setTimeout(() => { const mz = book(); if (mz) post({ type: 'mz-place', spread: mz.at() }) }, 200)
  }, { passive: true })
  addEventListener('resize', place)
  addEventListener('scroll', place, { passive: true })

  addEventListener('message', (e) => {
    const d = e.data as { type?: unknown; target?: FrameTarget; spread?: unknown } | null
    if (e.source !== parent || !d || typeof d.type !== 'string') return
    if (d.type === 'mz-goto') {
      // Once the page's own type has loaded (or a moment has passed): the
      // pages are measured with it, so the place found is where it stays,
      // and the editor shows this page without a flash of other type.
      let done = false
      const show = () => {
        if (done) return
        done = true
        const mz = book()
        mz?.refit()
        const el = elFor(d.target)
        if (el && d.target) select(d.target, el, 'now')
        else if (mz && typeof d.spread === 'number') mz.go(d.spread, true)
        reader.classList.add('mze-on')
        post({ type: 'mz-shown' })
      }
      ;(document.fonts?.ready ?? Promise.resolve()).then(show, show)
      setTimeout(show, 1500)
    } else if (d.type === 'mz-select' && d.target) {
      const to = elFor(d.target)
      select(d.target, to, to ? 'smooth' : null)
    }
  })

  reader.scrollIntoView({ block: 'start' })
  post({ type: 'mz-ready' })
}
