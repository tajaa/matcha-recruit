import { useLayoutEffect, useMemo, useRef, type DragEvent } from 'react'
import { dragging, dropOn, endDrag } from '../ui/add/drag'
import { landing } from '../ui/add/place'
import layoutCss from '../render/layout.css?raw'
import { facesCss, frameThreads, pageItemsHtml, type Draw } from '../render/layoutRender'
import { setHtml } from '../render/sink'
import { useStudio } from '../store/store'
import { useCtx } from '../ui/context'
import { Overlays } from './Overlays'
import { Rulers, RULER } from './Rulers'
import { TextOverlay } from './TextOverlay'
import { layout, type Layout } from './geometry'
import { usePointer } from './usePointer'

const PASTEBOARD = '#3a3a3d'

/** The pasteboard: every spread down the page, each page drawn by the page
 *  renderer (exactly as readers get it), with the Studio's guides and
 *  handles over it. Zoom with ⌘ and the wheel (or a pinch); pan with the
 *  wheel, the Hand tool or Space-drag. */
export default function Canvas() {
  const ctx = useCtx()
  const { store, fonts } = ctx
  const doc = useStudio(store, (s) => s.doc)
  const zoom = useStudio(store, (s) => s.view.zoom)
  const rulers = useStudio(store, (s) => s.view.rulers)
  const tool = useStudio(store, (s) => s.tool)
  const lay = useMemo(() => layout(doc), [doc])
  const scroller = useRef<HTMLDivElement>(null)
  const board = useRef<HTMLDivElement>(null)
  const pointer = usePointer(scroller, board, lay)

  const css = useMemo(() => layoutCss + facesCss(doc, fonts.book.face), [doc, fonts])
  const cursor = tool === 'hand' ? 'grab' : tool === 'zoom' ? 'zoom-in' : tool === 'select' ? 'default' : 'crosshair'
  const inset = rulers ? RULER : 0
  // Something dragged from the side panel lands where it is let go.
  const over = (e: DragEvent) => {
    if (!dragging(e.dataTransfer.types)) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }
  const drop = (e: DragEvent) => {
    const what = dragging(e.dataTransfer.types)
    if (!what) return
    e.preventDefault()
    endDrag()
    void dropOn(ctx, what, landing(ctx, e))
  }

  return (
    <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden" style={{ background: PASTEBOARD }}>
      <style>{css}</style>
      {rulers && <Rulers scroller={scroller} lay={lay} />}
      <div ref={scroller} data-studio-scroller onPointerDown={pointer.down} onDoubleClick={pointer.double} onDragOver={over} onDrop={drop}
        className="absolute overflow-auto overscroll-contain"
        style={{ left: inset, top: inset, right: 0, bottom: 0, cursor, touchAction: 'none', containerType: 'size' }}>
        <div className="w-max" style={{ padding: '50cqh 50cqw' }}>
          <div ref={board} data-studio-board className="relative"
            style={{ width: lay.width * zoom, height: lay.height * zoom, ['--u' as string]: `${zoom}px` }}>
            {lay.spreads.map((s) => (
              <div key={s.index} aria-hidden className="absolute" style={{
                left: s.x * zoom, top: s.y * zoom, width: s.w * zoom, height: s.h * zoom,
                background: doc.paper, boxShadow: '0 2px 14px rgba(0,0,0,.45)',
              }} />
            ))}
            <Pages lay={lay} />
            <Overlays lay={lay} />
            <TextOverlay />
          </div>
        </div>
      </div>
    </div>
  )
}

/** Each page drawn by the page renderer, written only when its HTML changed.
 *  Drawn before the text overlay reads the lines (its effect runs first). */
function Pages({ lay }: { lay: Layout }) {
  const { store, fonts } = useCtx()
  const doc = useStudio(store, (s) => s.doc)
  const zoom = useStudio(store, (s) => s.view.zoom)
  const assets = useStudio(store, (s) => s.assets)
  const pages = useRef<(HTMLDivElement | null)[]>([])
  useLayoutEffect(() => {
    const d: Draw = {
      assets, faces: fonts.book.face, used: new Map(), threads: frameThreads(doc),
      mark: (thread, k) => ` data-t="${thread.id}" data-k="${k}"`,
    }
    doc.pages.forEach((_, i) => {
      const el = pages.current[i]
      if (el) setHtml(el, pageItemsHtml(doc, i, d))
    })
  }, [doc, assets, fonts])
  return (
    <>
      {doc.pages.map((p, i) => (
        <div key={p.id} ref={(el) => { pages.current[i] = el }} data-studio-page={i}
          className="absolute" style={{ left: lay.origin[i].x * zoom, top: lay.origin[i].y * zoom,
            width: doc.size.w * zoom, height: doc.size.h * zoom }} />
      ))}
    </>
  )
}
