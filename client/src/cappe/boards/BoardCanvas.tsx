import { useEffect, useLayoutEffect, useRef, type DragEvent, type PointerEvent as RPointerEvent } from 'react'
import { Loader2, RotateCw } from 'lucide-react'
import type { Pin } from './api'
import { angleTo, clampCoord, resized, toBoard, zoomAt, type Point, type View } from './board'
import { fromTransfer, type Pasted } from './paste'
import PinView from './PinView'

/** A file or link on its way to the board, drawn where it will land. */
export interface Pending {
  key: string
  label: string
  x: number
  y: number
}

type Gesture =
  | { kind: 'pan'; sx: number; sy: number; view: View }
  | { kind: 'move'; pin: string; sx: number; sy: number; x: number; y: number }
  | { kind: 'resize'; pin: string; sx: number; sy: number; w: number; h: number }
  | { kind: 'rotate'; pin: string; centre: Point }

const DROPPABLE = ['Files', 'text/uri-list', 'text/plain']

/** The pinboard: a plane of pins you pan (drag the background, scroll) and
 *  zoom (⌘/Ctrl + scroll, pinch on a trackpad). A pin is dragged anywhere,
 *  over or beside the others; selected, it has a corner to size it and a
 *  handle to turn it. Files, links and words dropped on it land where they
 *  were dropped. Everything is reported up: the page owns the pins and saves. */
export default function BoardCanvas({
  pins, pending, view, onView, selected, editing, onPress, onChange, onRelease, onOpen, onEdit, onNoteDone,
  onDropped, onSize,
}: {
  pins: Pin[]
  pending: Pending[]
  view: View
  onView: (view: View) => void
  selected: string | null
  editing: string | null
  onPress: (id: string | null) => void
  onChange: (id: string, patch: Partial<Pin>) => void
  onRelease: () => void
  onOpen: (pin: Pin) => void
  onEdit: (id: string) => void
  onNoteDone: (id: string, text: string) => void
  onDropped: (what: Pasted, at: Point) => void
  onSize: (w: number, h: number) => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const gesture = useRef<Gesture | null>(null)
  const latest = useRef({ view, onView, onSize })
  useLayoutEffect(() => { latest.current = { view, onView, onSize } })

  const local = (e: { clientX: number; clientY: number }): Point => {
    const r = box.current?.getBoundingClientRect()
    return { x: e.clientX - (r?.left ?? 0), y: e.clientY - (r?.top ?? 0) }
  }

  // Scrolling pans and ⌘/Ctrl-scroll zooms; both must not scroll the page, so
  // the listener can't be passive (React's onWheel is).
  useEffect(() => {
    const el = box.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const { view: v, onView: set } = latest.current
      const p = local(e)
      // As the Studio's pages zoom (studio/canvas/usePointer.ts): a trackpad pinch
      // arrives as Ctrl-scroll in small steps, ⌘-scroll from a wheel in big ones.
      if (e.ctrlKey || e.metaKey) set(zoomAt(v, Math.exp(-e.deltaY * (e.ctrlKey && !e.metaKey ? 0.01 : 0.0025)), p.x, p.y))
      else set({ ...v, x: v.x - e.deltaX, y: v.y - e.deltaY })
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    const observer = typeof ResizeObserver === 'undefined' ? null
      : new ResizeObserver(([entry]) => latest.current.onSize(entry.contentRect.width, entry.contentRect.height))
    observer?.observe(el)
    latest.current.onSize(el.clientWidth, el.clientHeight)
    return () => { el.removeEventListener('wheel', onWheel); observer?.disconnect() }
  }, [])

  const capture = (e: RPointerEvent) => {
    try { box.current?.setPointerCapture(e.pointerId) } catch { /* jsdom, or the pointer is gone */ }
  }

  const startPan = (e: RPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    onPress(null)
    gesture.current = { kind: 'pan', sx: e.clientX, sy: e.clientY, view }
    capture(e)
  }

  const startPin = (e: RPointerEvent, pin: Pin, kind: 'move' | 'resize' | 'rotate') => {
    if (e.button !== 0 || editing === pin.id) return
    e.stopPropagation()
    onPress(pin.id)
    if (kind === 'move') gesture.current = { kind, pin: pin.id, sx: e.clientX, sy: e.clientY, x: pin.x, y: pin.y }
    else if (kind === 'resize') gesture.current = { kind, pin: pin.id, sx: e.clientX, sy: e.clientY, w: pin.w, h: pin.h }
    else {
      const el = (e.currentTarget as HTMLElement).closest('[data-pin]')?.getBoundingClientRect()
      const centre = el ? { x: el.left + el.width / 2, y: el.top + el.height / 2 } : { x: e.clientX, y: e.clientY + 40 }
      gesture.current = { kind, pin: pin.id, centre }
    }
    capture(e)
  }

  const move = (e: RPointerEvent) => {
    const g = gesture.current
    if (!g) return
    if (g.kind === 'pan') {
      onView({ ...g.view, x: g.view.x + e.clientX - g.sx, y: g.view.y + e.clientY - g.sy })
      return
    }
    const pin = pins.find((p) => p.id === g.pin)
    if (!pin) return
    if (g.kind === 'move') {
      onChange(g.pin, { x: clampCoord(g.x + (e.clientX - g.sx) / view.zoom), y: clampCoord(g.y + (e.clientY - g.sy) / view.zoom) })
    } else if (g.kind === 'resize') {
      onChange(g.pin, resized(pin, g.w + (e.clientX - g.sx) / view.zoom, g.h + (e.clientY - g.sy) / view.zoom, e.shiftKey))
    } else {
      onChange(g.pin, { rotation: angleTo(g.centre, { x: e.clientX, y: e.clientY }) })
    }
  }

  const end = () => {
    const g = gesture.current
    gesture.current = null
    if (g && g.kind !== 'pan') onRelease()
  }

  const over = (e: DragEvent) => {
    if (DROPPABLE.some((t) => e.dataTransfer.types.includes(t))) {
      e.preventDefault()
      e.dataTransfer.dropEffect = 'copy'
    }
  }

  const drop = (e: DragEvent) => {
    const what = fromTransfer(e.dataTransfer)
    if (!what) return
    e.preventDefault()
    const p = local(e)
    onDropped(what, toBoard(view, p.x, p.y))
  }

  // Double-click or Enter: write on a note, open anything else.
  const activate = (pin: Pin) => {
    if (pin.kind === 'note') onEdit(pin.id)
    else onOpen(pin)
  }

  const grid = 24 * view.zoom
  return (
    <div
      ref={box}
      data-testid="board-canvas"
      onPointerDown={startPan}
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
      onDragOver={over}
      onDrop={drop}
      className="relative h-full w-full cursor-grab touch-none select-none overflow-hidden bg-zinc-950 active:cursor-grabbing"
      style={{
        backgroundImage: 'radial-gradient(circle, rgb(63 63 70 / 0.7) 1px, transparent 1px)',
        backgroundSize: `${grid}px ${grid}px`,
        backgroundPosition: `${view.x}px ${view.y}px`,
      }}
    >
      <div className="absolute left-0 top-0 origin-top-left"
        style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})` }}>
        {pins.map((pin) => (
          <div
            key={pin.id}
            data-pin={pin.id}
            role="button"
            tabIndex={0}
            aria-label={label(pin)}
            aria-pressed={selected === pin.id}
            onPointerDown={(e) => startPin(e, pin, 'move')}
            onDoubleClick={() => activate(pin)}
            onKeyDown={(e) => { if (e.key === 'Enter' && editing !== pin.id) { e.preventDefault(); activate(pin) } }}
            onFocus={() => { if (selected !== pin.id && !gesture.current) onPress(pin.id) }}
            className="absolute cursor-move outline-none"
            style={{ left: pin.x, top: pin.y, width: pin.w, height: pin.h, zIndex: pin.z, transform: `rotate(${pin.rotation}deg)` }}
          >
            <PinView pin={pin} editing={editing === pin.id} onNoteDone={(text) => onNoteDone(pin.id, text)} />
            {selected === pin.id && editing !== pin.id && (
              <>
                <span aria-hidden className="pointer-events-none absolute -inset-1 rounded ring-2 ring-emerald-400" />
                <span aria-hidden title="Turn" onPointerDown={(e) => startPin(e, pin, 'rotate')}
                  className="absolute -top-8 left-1/2 flex h-6 w-6 cursor-grab items-center justify-center rounded-full bg-emerald-400 text-zinc-950 shadow"
                  style={{ transform: `translateX(-50%) scale(${1 / view.zoom})` }}>
                  <RotateCw className="h-3.5 w-3.5" />
                </span>
                <span aria-hidden title="Size (Shift: any shape)" onPointerDown={(e) => startPin(e, pin, 'resize')}
                  className="absolute -bottom-2 -right-2 h-4 w-4 cursor-nwse-resize rounded-full border-2 border-zinc-950 bg-emerald-400 shadow"
                  style={{ transform: `scale(${1 / view.zoom})` }} />
              </>
            )}
          </div>
        ))}
        {pending.map((p) => (
          <div key={p.key} className="absolute flex h-32 w-52 flex-col items-center justify-center gap-2 rounded-md border border-dashed border-zinc-600 bg-zinc-900/80 p-3 text-center text-xs text-zinc-400"
            style={{ left: p.x, top: p.y, zIndex: 1_000_001 }}>
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            <span className="line-clamp-2 break-all">{p.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function label(pin: Pin): string {
  switch (pin.kind) {
    case 'note': return `Note: ${(pin.note ?? '').slice(0, 60)}`
    case 'image': return `Picture${pin.alt ? `: ${pin.alt}` : pin.filename ? `: ${pin.filename}` : ''}`
    case 'link': return `Link: ${pin.title || pin.url}`
    default: return `File: ${pin.title || pin.filename}`
  }
}
