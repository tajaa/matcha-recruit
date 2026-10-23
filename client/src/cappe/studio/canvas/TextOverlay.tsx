import { useLayoutEffect, useRef } from 'react'
import { order } from '../model/ops'
import { useStudio } from '../store/store'
import { caretAt, selectionRects } from '../text/caret'
import { useCtx } from '../ui/context'

/** The caret and the selected text while typing, read from the page as drawn
 *  (after it is drawn), and the hidden input moved to the caret so an IME's
 *  window opens there. */
export function TextOverlay() {
  const { store, board, editor } = useCtx()
  const doc = useStudio(store, (s) => s.doc)
  const editing = useStudio(store, (s) => s.editing)
  const zoom = useStudio(store, (s) => s.view.zoom)
  const layer = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const el = layer.current
    const root = board()
    if (!el || !root) return
    el.replaceChildren()
    if (!editing) return
    const thread = doc.threads.find((t) => t.id === editing.thread)
    if (!thread?.comp) return
    const origin = root.getBoundingClientRect()
    const [a, b] = order(editing.anchor, editing.head)
    const box = (left: number, top: number, width: number, height: number, bg: string, blink = false) => {
      const d = document.createElement('div')
      d.style.cssText = `position:absolute;left:${left - origin.left}px;top:${top - origin.top}px;width:${width}px;height:${height}px;background:${bg};pointer-events:none`
      if (blink) d.className = 'st-caret'
      el.appendChild(d)
      return d
    }
    if (a[0] !== b[0] || a[1] !== b[1]) {
      for (const r of selectionRects(root, thread, a, b)) {
        box(r.left, r.base - r.size * 0.95, Math.max(1, r.right - r.left), r.size * 1.25, 'rgba(16,185,129,.32)')
      }
    }
    const at = caretAt(root, thread, editing.head[0], editing.head[1])
    if (!at) return
    const line = root.querySelector<HTMLElement>(`.lyt-l[data-t="${thread.id}"][data-k="${at.k}"]`)
    const size = parseFloat(getComputedStyle(line?.firstElementChild ?? line ?? root).fontSize) || 12 * zoom
    if (a[0] === b[0] && a[1] === b[1]) box(at.x - 0.75, at.base - size * 0.92, 1.5, size * 1.15, '#10b981', true)
    editor.moveInput(at.x, at.base - size)
  }, [doc, editing, zoom, board, editor])

  return <div ref={layer} aria-hidden className="pointer-events-none absolute inset-0" />
}
