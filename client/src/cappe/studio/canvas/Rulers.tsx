import { useLayoutEffect, useRef, type RefObject } from 'react'
import { addGuide } from '../model/ops'
import type { Units } from '../model/types'
import { PT_PER } from '../model/units'
import { useStudio } from '../store/store'
import { useCtx } from '../ui/context'
import { boardOffset, pageAt, type Layout } from './geometry'

export const RULER = 20

const STEPS = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000]

/** The rulers along the top and the left, in the document's units, counted
 *  from the top-left of the spread in view. Drag out of one to make a guide
 *  on the page you drop it on (drag a guide back onto a ruler to remove it). */
export function Rulers({ scroller, lay }: { scroller: RefObject<HTMLDivElement | null>; lay: Layout }) {
  const { store } = useCtx()
  const doc = useStudio(store, (s) => s.doc)
  const zoom = useStudio(store, (s) => s.view.zoom)
  const top = useRef<HTMLCanvasElement>(null)
  const left = useRef<HTMLCanvasElement>(null)

  useLayoutEffect(() => {
    const sc = scroller.current
    if (!sc) return
    const draw = () => {
      const o = boardOffset(sc)
      const centreY = (sc.scrollTop - o.y + sc.clientHeight / 2) / zoom
      const spread = lay.spreads.find((s) => centreY <= s.y + s.h + 24) ?? lay.spreads[lay.spreads.length - 1]
      if (!spread) return
      const ox = o.x + lay.origin[spread.pages[0]].x * zoom - sc.scrollLeft
      const oy = o.y + spread.y * zoom - sc.scrollTop
      paint(top.current, 'x', ox, doc.units, zoom)
      paint(left.current, 'y', oy, doc.units, zoom)
    }
    draw()
    sc.addEventListener('scroll', draw, { passive: true })
    const ro = new ResizeObserver(draw)
    ro.observe(sc)
    return () => { sc.removeEventListener('scroll', draw); ro.disconnect() }
  }, [scroller, lay, zoom, doc.units])

  const drag = (axis: 'v' | 'h') => (e: React.PointerEvent) => {
    const sc = scroller.current
    if (!sc) return
    e.preventDefault()
    const line = document.createElement('div')
    line.style.cssText = `position:fixed;pointer-events:none;background:#22d3ee;z-index:60;${axis === 'v' ? 'top:0;bottom:0;width:1px' : 'left:0;right:0;height:1px'}`
    document.body.appendChild(line)
    const move = (ev: PointerEvent) => {
      if (axis === 'v') line.style.left = `${ev.clientX}px`
      else line.style.top = `${ev.clientY}px`
    }
    const up = (ev: PointerEvent) => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      line.remove()
      const r = sc.getBoundingClientRect()
      if (ev.clientX < r.left || ev.clientY < r.top) return // back on a ruler
      const b = boardOffset(sc)
      const p = { x: (ev.clientX - r.left + sc.scrollLeft - b.x) / zoom, y: (ev.clientY - r.top + sc.scrollTop - b.y) / zoom }
      const page = pageAt(doc, lay, p)
      const o = lay.origin[page]
      store.edit((d) => addGuide(d, d.pages[page].id, axis, axis === 'v' ? p.x - o.x : p.y - o.y).doc)
    }
    move(e.nativeEvent)
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  return (
    <>
      <div className="absolute left-0 top-0 z-10 border-b border-r border-zinc-700 bg-zinc-900" style={{ width: RULER, height: RULER }} />
      <canvas ref={top} onPointerDown={drag('h')} aria-label="Ruler: drag down for a guide"
        className="absolute top-0 z-10 cursor-row-resize border-b border-zinc-700" style={{ left: RULER, right: 0, height: RULER, width: `calc(100% - ${RULER}px)` }} />
      <canvas ref={left} onPointerDown={drag('v')} aria-label="Ruler: drag right for a guide"
        className="absolute left-0 z-10 cursor-col-resize border-r border-zinc-700" style={{ top: RULER, bottom: 0, width: RULER, height: `calc(100% - ${RULER}px)` }} />
    </>
  )
}

function paint(canvas: HTMLCanvasElement | null, axis: 'x' | 'y', origin: number, units: Units, zoom: number) {
  if (!canvas) return
  const dpr = window.devicePixelRatio || 1
  const len = axis === 'x' ? canvas.clientWidth : canvas.clientHeight
  const w = axis === 'x' ? len : RULER, h = axis === 'x' ? RULER : len
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr)
    canvas.height = Math.round(h * dpr)
  }
  const g = canvas.getContext('2d')
  if (!g) return
  g.setTransform(dpr, 0, 0, dpr, 0, 0)
  g.fillStyle = '#18181b'
  g.fillRect(0, 0, w, h)
  const unit = PT_PER[units] * zoom // px per unit
  const major = STEPS.find((s) => s * unit >= 56) ?? STEPS[STEPS.length - 1]
  const minor = major / (major % 5 === 0 ? 5 : major % 2 === 0 ? 4 : 2)
  g.strokeStyle = '#71717a'
  g.fillStyle = '#a1a1aa'
  g.font = '9px system-ui, sans-serif'
  g.lineWidth = 1
  const first = Math.floor(-origin / (minor * unit)) - 1
  const last = Math.ceil((len - origin) / (minor * unit)) + 1
  g.beginPath()
  for (let k = first; k <= last; k++) {
    const v = k * minor
    const at = Math.round(origin + v * unit) + 0.5
    const isMajor = Math.abs(v / major - Math.round(v / major)) < 1e-6
    const tick = isMajor ? RULER : RULER * 0.3
    if (axis === 'x') { g.moveTo(at, RULER); g.lineTo(at, RULER - tick) } else { g.moveTo(RULER, at); g.lineTo(RULER - tick, at) }
    if (isMajor) {
      const label = String(Math.round(v * 100) / 100)
      if (axis === 'x') g.fillText(label, at + 2, 9)
      else {
        g.save()
        g.translate(9, at + 2)
        g.rotate(-Math.PI / 2)
        g.fillText(label, -g.measureText(label).width - 2, 0)
        g.restore()
      }
    }
  }
  g.stroke()
}
