import { useEffect, useLayoutEffect, useRef, type RefObject } from 'react'
import { pageSide } from '../model/doc'
import { clamp, round } from '../model/limits'
import { addItem, deleteGuide, duplicate, ensureThread, link, moveGuide, patchItems, unlinkAfter, updateItems } from '../model/ops'
import type { Doc, Item, Kind } from '../model/types'
import { placeAt } from '../text/caret'
import { useStudio } from '../store/store'
import { useCtx } from '../ui/context'
import { boardOffset, bounds, centre, hitItem, itemBox, pageAt, snap1, snapTargets, type Layout, type Pt } from './geometry'
import { dragBox, resize, rotate } from './transform'

const ZOOM_MIN = 0.05, ZOOM_MAX = 64
const CREATE: Partial<Record<string, Kind>> = { frame: 'image', rect: 'rect', ellipse: 'ellipse', line: 'line', text: 'text' }

/** The canvas's pointer: every tool's clicks and drags, the wheel's zoom,
 *  Space to pan. Reads the store as it is at each event (never stale), and
 *  writes it through `edit` (one undo step a drag). */
export function usePointer(scroller: RefObject<HTMLDivElement | null>, board: RefObject<HTMLDivElement | null>, lay: Layout) {
  const ctx = useCtx()
  const { store, editor } = ctx
  const layRef = useRef(lay)
  const pending = useRef<{ x: number; y: number } | null>(null)
  const space = useRef(false)
  const zoomRef = useRef<(cx: number, cy: number, f: number) => void>(() => {})
  const z = useStudio(store, (s) => s.view.zoom)

  useLayoutEffect(() => {
    layRef.current = lay
    zoomRef.current = zoomAt
  })

  // A zoom keeps the point it was asked at under the pointer (once the board
  // has its new size).
  useLayoutEffect(() => {
    const sc = scroller.current
    if (sc && pending.current) {
      sc.scrollLeft = pending.current.x
      sc.scrollTop = pending.current.y
      pending.current = null
    }
  }, [z, scroller])

  useEffect(() => {
    const sc = scroller.current
    if (!sc) return
    const wheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return
      e.preventDefault()
      zoomRef.current(e.clientX, e.clientY, Math.exp(-e.deltaY * (e.ctrlKey && !e.metaKey ? 0.01 : 0.0025)))
    }
    const key = (down: boolean) => (e: KeyboardEvent) => {
      if (e.code !== 'Space' || store.get().editing) return
      const t = e.target as HTMLElement | null
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return
      space.current = down
      sc.style.cursor = down ? 'grab' : ''
      if (down) e.preventDefault()
    }
    const kd = key(true), ku = key(false)
    sc.addEventListener('wheel', wheel, { passive: false })
    window.addEventListener('keydown', kd)
    window.addEventListener('keyup', ku)
    return () => { sc.removeEventListener('wheel', wheel); window.removeEventListener('keydown', kd); window.removeEventListener('keyup', ku) }
  }, [store, scroller])

  const zoom = () => store.get().view.zoom

  const toPt = (e: { clientX: number; clientY: number }): Pt => {
    const r = board.current!.getBoundingClientRect()
    return { x: (e.clientX - r.left) / zoom(), y: (e.clientY - r.top) / zoom() }
  }

  /** Zoom by `factor` keeping the point under (cx, cy) in place. */
  function zoomAt(cx: number, cy: number, factor: number): void {
    const sc = scroller.current
    if (!sc) return
    const p = toPt({ clientX: cx, clientY: cy })
    const next = clamp(zoom() * factor, ZOOM_MIN, ZOOM_MAX)
    const r = sc.getBoundingClientRect()
    const o = boardOffset(sc)
    pending.current = { x: o.x + p.x * next - (cx - r.left), y: o.y + p.y * next - (cy - r.top) }
    store.set((s) => ({ view: { ...s.view, zoom: next } }))
  }

  /** Follow a drag from `e`: `move` once it has moved 3 px, then `up`. */
  function drag(e: React.PointerEvent, move: (p: Pt, ev: PointerEvent) => void,
    up?: (p: Pt, ev: PointerEvent, moved: boolean) => void): void {
    const el = scroller.current!
    el.setPointerCapture(e.pointerId)
    const start = toPt(e)
    let moved = false
    const onMove = (ev: PointerEvent) => {
      const p = toPt(ev)
      if (!moved && Math.hypot(p.x - start.x, p.y - start.y) * zoom() < 3) return
      moved = true
      move(p, ev)
    }
    const onUp = (ev: PointerEvent) => {
      el.removeEventListener('pointermove', onMove)
      el.removeEventListener('pointerup', onUp)
      el.removeEventListener('pointercancel', onUp)
      up?.(toPt(ev), ev, moved)
      store.seal()
      store.set({ snaps: null, marquee: null })
    }
    el.addEventListener('pointermove', onMove)
    el.addEventListener('pointerup', onUp)
    el.addEventListener('pointercancel', onUp)
  }

  const origin = (doc: Doc, item: Item) => layRef.current.origin[doc.pages.findIndex((p) => p.id === item.page)]

  // ── tools ────────────────────────────────────────────────────────────────

  function pan(e: React.PointerEvent): void {
    const sc = scroller.current!
    const x0 = e.clientX, y0 = e.clientY, l0 = sc.scrollLeft, t0 = sc.scrollTop
    sc.setPointerCapture(e.pointerId)
    const move = (ev: PointerEvent) => { sc.scrollLeft = l0 - (ev.clientX - x0); sc.scrollTop = t0 - (ev.clientY - y0) }
    const up = () => { sc.removeEventListener('pointermove', move); sc.removeEventListener('pointerup', up) }
    sc.addEventListener('pointermove', move)
    sc.addEventListener('pointerup', up)
  }

  function moveItems(e: React.PointerEvent, start: Pt): void {
    let s = store.get()
    let ids = s.selection.filter((id) => !s.doc.items.find((i) => i.id === id)?.locked)
    if (!ids.length) return
    let copied = false
    const startPos = new Map(s.doc.items.filter((i) => ids.includes(i.id)).map((i) => [i.id, { x: i.x, y: i.y }]))
    drag(e, (p, ev) => {
      if (ev.altKey && !copied) {
        // Alt-drag leaves the originals and moves copies.
        copied = true
        let made: string[] = []
        store.edit((d) => { const r = duplicate(d, ids, 0, 0); made = r.ids; return r.doc }, { key: 'move' })
        ids.forEach((id, k) => startPos.set(made[k], startPos.get(id)!))
        ids = made
        store.set({ selection: made })
      }
      s = store.get()
      let dx = p.x - start.x, dy = p.y - start.y
      if (ev.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) dy = 0; else dx = 0 }
      const moving = s.doc.items.filter((i) => ids.includes(i.id))
      const snaps: { x: number[]; y: number[] } = { x: [], y: [] }
      if (s.view.snap && moving.length) {
        const placed = moving.map((i) => ({ ...i, x: startPos.get(i.id)!.x + dx, y: startPos.get(i.id)!.y + dy }))
        const b = bounds(placed, (i) => origin(s.doc, i))!
        const page = pageAt(s.doc, layRef.current, centre(b))
        const t = snapTargets(s.doc, layRef.current, page, new Set(ids))
        const tol = 6 / zoom()
        const sx = snap1([b.x, b.x + b.w / 2, b.x + b.w], t.x, tol)
        const sy = snap1([b.y, b.y + b.h / 2, b.y + b.h], t.y, tol)
        dx += sx.d
        dy += sy.d
        if (sx.at !== null) snaps.x.push(sx.at)
        if (sy.at !== null) snaps.y.push(sy.at)
      }
      store.edit((d) => updateItems(d, ids, (i) => ({ ...i, x: round(startPos.get(i.id)!.x + dx), y: round(startPos.get(i.id)!.y + dy) })),
        { key: 'move', extra: { snaps } })
    }, (_p, _ev, moved) => {
      if (!moved) return
      // An item dropped on another page goes onto it.
      store.edit((d) => {
        let next = d
        for (const id of ids) {
          const item = next.items.find((i) => i.id === id)
          if (!item) continue
          const o = origin(next, item)
          const c = centre(itemBox(item, o))
          const page = pageAt(next, layRef.current, c)
          const pid = next.pages[page].id
          if (pid === item.page) continue
          const no = layRef.current.origin[page]
          next = updateItems(next, [id], (i) => ({ ...i, page: pid, x: round(i.x + o.x - no.x), y: round(i.y + o.y - no.y) }))
        }
        return next
      }, { key: 'move' })
    })
  }

  function resizeItem(e: React.PointerEvent, start: Pt, handle: string): void {
    const s0 = store.get()
    const item = s0.doc.items.find((i) => i.id === s0.selection[0])
    if (!item) return
    const geo = { x: item.x, y: item.y, w: item.w, h: item.h, rot: item.rot }
    const o = origin(s0.doc, item)
    drag(e, (p, ev) => {
      const s = store.get()
      const next = resize(geo, handle, p.x - start.x, p.y - start.y,
        { keep: ev.shiftKey, fromCentre: ev.altKey, min: item.kind === 'line' ? 0 : 1 })
      const snaps: { x: number[]; y: number[] } = { x: [], y: [] }
      if (s.view.snap && !geo.rot && !ev.altKey) {
        const t = snapTargets(s.doc, layRef.current, s.doc.pages.findIndex((pg) => pg.id === item.page), new Set([item.id]))
        const tol = 6 / zoom()
        if (handle.includes('w')) { const r = snap1([o.x + next.x], t.x, tol); next.x += r.d; next.w -= r.d; if (r.at !== null) snaps.x.push(r.at) }
        if (handle.includes('e')) { const r = snap1([o.x + next.x + next.w], t.x, tol); next.w += r.d; if (r.at !== null) snaps.x.push(r.at) }
        if (handle.includes('n')) { const r = snap1([o.y + next.y], t.y, tol); next.y += r.d; next.h -= r.d; if (r.at !== null) snaps.y.push(r.at) }
        if (handle.includes('s')) { const r = snap1([o.y + next.y + next.h], t.y, tol); next.h += r.d; if (r.at !== null) snaps.y.push(r.at) }
      }
      store.edit((d) => patchItems(d, [item.id], { x: next.x, y: next.y, w: Math.max(0, next.w), h: Math.max(0, next.h) }),
        { key: `resize:${item.id}`, extra: { snaps } })
    })
  }

  function rotateItem(e: React.PointerEvent, start: Pt): void {
    const s0 = store.get()
    const item = s0.doc.items.find((i) => i.id === s0.selection[0])
    if (!item) return
    const c = centre(itemBox(item, origin(s0.doc, item)))
    drag(e, (p, ev) => {
      store.edit((d) => patchItems(d, [item.id], { rot: rotate(item.rot, c, start, p, ev.shiftKey) }), { key: `rot:${item.id}` })
    })
  }

  /** Drag out a new frame or shape (a click makes one of a standard size). */
  function create(e: React.PointerEvent, start: Pt, kind: Kind): void {
    const s0 = store.get()
    const page = pageAt(s0.doc, layRef.current, start)
    const o = layRef.current.origin[page]
    const pid = s0.doc.pages[page].id
    let id: string | null = null
    const place = (box: { x: number; y: number; w: number; h: number; flip?: boolean }) => {
      const local = { x: box.x - o.x, y: box.y - o.y, w: box.w, h: box.h }
      if (!id) {
        store.edit((d) => { const r = addItem(d, kind, pid, local); id = r.id; return r.doc }, { key: 'create' })
        if (kind === 'line' && box.flip) store.edit((d) => patchItems(d, [id!], { flip: true }), { key: 'create' })
      } else store.edit((d) => patchItems(d, [id!], { ...local, ...(kind === 'line' ? { flip: !!box.flip } : {}) }), { key: 'create' })
    }
    drag(e, (p, ev) => {
      const box = dragBox(start, p, { square: ev.shiftKey, line: kind === 'line' })
      if (kind !== 'line') { box.w = Math.max(box.w, 1); box.h = Math.max(box.h, 1) }
      place(box)
    }, (_p, _ev, moved) => {
      if (!moved) place(defaultBox(store.get().doc, page, start, o, kind))
      if (!id) return
      store.set({ selection: [id], tool: 'select' })
      if (kind === 'text') startTyping(id, null)
      if (kind === 'image') store.set({ dialog: 'library' })
    })
  }

  /** Type in a text frame: at the place clicked, or its start. */
  function startTyping(frame: string, at: { clientX: number; clientY: number } | null): void {
    let thread = ''
    store.edit((d) => { const r = ensureThread(d, frame); thread = r.thread; return r.doc })
    const t = store.get().doc.threads.find((x) => x.id === thread)
    const root = board.current
    const pos = t && root && at ? placeAt(root, t, at.clientX, at.clientY) : null
    store.set({ selection: [frame], tool: store.get().tool === 'text' ? 'text' : 'select' })
    editor.open(thread, pos ?? [0, 0])
  }

  function threadInto(p: Pt): void {
    const s = store.get()
    const from = s.threading!.frame
    const hit = hitItem(s.doc, layRef.current, p)
    if (hit?.kind === 'text') store.edit((d) => link(d, from, hit.id))
    else {
      // Somewhere empty: a new frame there, the width of the column under it.
      const page = pageAt(s.doc, layRef.current, p)
      const box = defaultBox(s.doc, page, p, layRef.current.origin[page], 'text')
      let id = ''
      store.edit((d) => {
        const r = addItem(d, 'text', d.pages[page].id, { x: box.x - layRef.current.origin[page].x,
          y: box.y - layRef.current.origin[page].y, w: box.w, h: box.h })
        id = r.id
        return link(r.doc, from, r.id)
      })
      store.set({ selection: [id] })
    }
    store.set({ threading: null })
  }

  function guideAt(p: Pt): { id: string; axis: 'v' | 'h'; page: number } | null {
    const s = store.get()
    if (!s.view.guides) return null
    const tol = 4 / zoom()
    for (const g of s.doc.guides) {
      const page = s.doc.pages.findIndex((pg) => pg.id === g.page)
      const o = layRef.current.origin[page]
      if (!o) continue
      const inside = p.x >= o.x && p.x <= o.x + s.doc.size.w && p.y >= o.y && p.y <= o.y + s.doc.size.h
      if (inside && Math.abs(g.axis === 'v' ? p.x - (o.x + g.at) : p.y - (o.y + g.at)) <= tol) return { id: g.id, axis: g.axis, page }
    }
    return null
  }

  function moveGuideDrag(e: React.PointerEvent, g: { id: string; axis: 'v' | 'h'; page: number }): void {
    const o = layRef.current.origin[g.page]
    drag(e, (p) => {
      store.edit((d) => moveGuide(d, g.id, g.axis === 'v' ? p.x - o.x : p.y - o.y), { key: `guide:${g.id}` })
    }, (p, _ev, moved) => {
      const { w, h } = store.get().doc.size
      const off = p.x < o.x - 24 || p.x > o.x + w + 24 || p.y < o.y - 24 || p.y > o.y + h + 24
      if (moved && off) store.edit((d) => deleteGuide(d, g.id), { key: `guide:${g.id}` })
    })
  }

  function marquee(e: React.PointerEvent, start: Pt): void {
    const before = e.shiftKey ? store.get().selection : []
    drag(e, (p) => {
      store.set({ marquee: { x: Math.min(start.x, p.x), y: Math.min(start.y, p.y), w: Math.abs(p.x - start.x), h: Math.abs(p.y - start.y) } })
    }, (_p, _ev, moved) => {
      const m = store.get().marquee
      if (!moved || !m) { store.set({ selection: before }); return }
      const s = store.get()
      const inside = s.doc.items.filter((i) => {
        if (i.hidden || i.locked) return false
        const b = bounds([i], (x) => origin(s.doc, x))!
        return b.x < m.x + m.w && b.x + b.w > m.x && b.y < m.y + m.h && b.y + b.h > m.y
      }).map((i) => i.id)
      store.set({ selection: [...new Set([...before, ...inside])] })
    })
  }

  // ── events ───────────────────────────────────────────────────────────────

  function down(e: React.PointerEvent): void {
    const s = store.get()
    if (e.button === 1 || space.current || s.tool === 'hand') { e.preventDefault(); pan(e); return }
    if (e.button !== 0) return
    const p = toPt(e)
    const target = e.target as HTMLElement
    const lay = layRef.current

    if (s.editing) {
      const thread = s.doc.threads.find((t) => t.id === s.editing!.thread)
      const hit = hitItem(s.doc, lay, p)
      if (thread && hit && thread.frames.includes(hit.id) && board.current) {
        e.preventDefault()
        const at = placeAt(board.current, thread, e.clientX, e.clientY)
        if (at) editor.place(at, e.shiftKey)
        drag(e, (_q, ev) => {
          const t = store.get().doc.threads.find((x) => x.id === thread.id)
          const to = t && board.current ? placeAt(board.current, t, ev.clientX, ev.clientY) : null
          if (to) editor.place(to, true)
        })
        return
      }
      editor.close()
    }

    if (s.tool === 'zoom') { zoomAt(e.clientX, e.clientY, e.altKey ? 1 / 1.6 : 1.6); return }
    if (s.tool === 'text') {
      const hit = hitItem(s.doc, lay, p)
      if (hit?.kind === 'text') { e.preventDefault(); startTyping(hit.id, e); return }
      create(e, p, 'text')
      return
    }
    const kind = CREATE[s.tool]
    if (kind) { create(e, p, kind); return }

    // The selection tool.
    if (s.threading) { threadInto(p); return }
    const port = target.closest<HTMLElement>('[data-port]')
    if (port) {
      const frame = port.dataset.frame!
      if (port.dataset.port === 'out') store.set({ threading: { thread: null, frame } })
      else {
        const t = s.doc.threads.find((x) => x.frames.includes(frame))
        const at = t ? t.frames.indexOf(frame) : -1
        if (t && at > 0) store.edit((d) => unlinkAfter(d, t.frames[at - 1]))
      }
      return
    }
    const handle = target.closest<HTMLElement>('[data-handle]')?.dataset.handle
    if (handle) { e.preventDefault(); if (handle === 'rot') rotateItem(e, p); else resizeItem(e, p, handle); return }
    const hit = hitItem(s.doc, lay, p, 3 / zoom())
    if (hit) {
      e.preventDefault()
      if (e.shiftKey) {
        store.set({ selection: s.selection.includes(hit.id) ? s.selection.filter((x) => x !== hit.id) : [...s.selection, hit.id] })
        return
      }
      if (!s.selection.includes(hit.id)) store.set({ selection: [hit.id] })
      store.set({ page: s.doc.pages.findIndex((pg) => pg.id === hit.page) })
      moveItems(e, p)
      return
    }
    const guide = guideAt(p)
    if (guide) { moveGuideDrag(e, guide); return }
    store.set({ page: pageAt(s.doc, lay, p) })
    marquee(e, p)
  }

  function double(e: React.MouseEvent): void {
    const s = store.get()
    if (s.tool !== 'select' && s.tool !== 'text') return
    const hit = hitItem(s.doc, layRef.current, toPt(e))
    if (hit?.kind === 'text' && !hit.locked) startTyping(hit.id, e)
    else if (hit?.kind === 'image' && !hit.locked) store.set({ selection: [hit.id], dialog: 'library' })
  }

  return { down, double, zoomAt }
}

/** A frame or shape made by a click: a standard size there; a text frame the
 *  width of the column clicked and down to the bottom margin. */
function defaultBox(doc: Doc, page: number, p: Pt, o: Pt, kind: Kind) {
  if (kind !== 'text') {
    const size = kind === 'line' ? { w: 144, h: 0 } : { w: 144, h: 144 }
    return { x: p.x, y: p.y, ...size, flip: false }
  }
  const { w, h } = doc.size
  const m = doc.margins
  const left = pageSide(doc, page) === 'left'
  const ml = left ? m.o : m.i, mr = left ? m.i : m.o
  const cw = (w - ml - mr - doc.cols.g * (doc.cols.n - 1)) / doc.cols.n
  const lx = p.x - o.x
  const col = clamp(Math.floor((lx - ml) / (cw + doc.cols.g)), 0, doc.cols.n - 1)
  const x = o.x + ml + col * (cw + doc.cols.g)
  const y = clamp(p.y, o.y + m.t, o.y + h - m.b - 24)
  return { x, y, w: cw, h: Math.max(24, o.y + h - m.b - y), flip: false }
}
