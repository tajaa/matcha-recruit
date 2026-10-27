// The right-click menu: what can be done to the thing under the pointer (or
// to the page, on an empty part of it), each row a command with its key, as
// the menus have it. Also opened by the selection bar's "More". Arrows move
// through it, → and ← open and close a side menu, Esc closes it.

import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { ChevronRight } from 'lucide-react'
import { useStudio, type State } from '../store/store'
import { command, type Command } from './commands'
import { useCtx } from './context'
import { menuRows, type Row } from './menuRows'

/** The menu at `store.menu`, kept inside the window. */
export default function ContextMenu() {
  const c = useCtx()
  const at = useStudio(c.store, (s) => s.menu ?? null)
  const state = useStudio(c.store, (s) => s)
  const root = useRef<HTMLDivElement>(null)
  const close = () => c.store.set({ menu: null })

  // Closed by a click elsewhere, leaving the window, a resize, and the page
  // moving under it (a scroll, or the wheel or a pinch zooming).
  useEffect(() => {
    if (!at) return
    const gone = () => c.store.set({ menu: null })
    const away = (e: Event) => { if (!root.current?.contains(e.target as Node)) gone() }
    const events: [string, EventListener, boolean][] = [
      ['pointerdown', away, true], ['wheel', away, true], ['scroll', away, true], ['blur', gone, false], ['resize', gone, false],
    ]
    for (const [name, fn, capture] of events) window.addEventListener(name, fn, capture)
    return () => { for (const [name, fn, capture] of events) window.removeEventListener(name, fn, capture) }
  }, [at, c.store])

  if (!at) return null
  return (
    // A press on the menu's gaps or a dimmed row leaves the keyboard on the
    // row it was on, so the arrows and Esc keep working.
    <div ref={root} onContextMenu={(e) => e.preventDefault()} onMouseDown={(e) => e.preventDefault()}>
      <Menu rows={menuRows(state)} state={state} x={at.x} y={at.y} focus onClose={close}
        run={(cmd) => { close(); cmd.run(c) }} />
    </div>
  )
}

function Menu({ rows, state, x, y, back, focus, onClose, onBack, run }: {
  rows: Row[]; state: State; x: number; y: number
  /** A side menu: the left edge of the menu it came out of (flipped, it ends there). */
  back?: number
  /** Take the keyboard when it opens (the menu, and a side menu opened by key). */
  focus: boolean
  onClose: () => void
  /** A side menu's way back to the menu it came out of. */
  onBack?: () => void
  run: (cmd: Command) => void
}) {
  const el = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ left: x, top: y })
  // The side menu out, and where (measured from its row when it opened:
  // `x` its right edge, `back` its left, where a flipped side menu ends).
  const [open, setOpen] = useState<{ index: number; byKey: boolean; x: number; y: number; back: number } | null>(null)
  const openAt = (index: number, byKey: boolean, row: HTMLElement) => {
    const r = row.getBoundingClientRect()
    setOpen({ index, byKey, x: r.right - 2, y: r.top - 5, back: r.left + 2 })
  }

  // Kept inside the window: flipped to the left or up when it would run off
  // (a side menu to the left of the menu it came out of, whatever its width).
  useLayoutEffect(() => {
    const m = el.current
    if (!m) return
    const w = m.offsetWidth, h = m.offsetHeight
    const left = x + w > window.innerWidth - 4 ? Math.max(4, (back ?? x) - w) : x
    const top = y + h > window.innerHeight - 4 ? Math.max(4, window.innerHeight - h - 4) : y
    setPos({ left, top })
    if (focus) m.querySelector<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')?.focus()
  }, [x, y, back, focus])

  const buttons = () => [...(el.current?.querySelectorAll<HTMLButtonElement>(':scope > [role="menuitem"]:not(:disabled)') ?? [])]
  const keys = (e: ReactKeyboardEvent) => {
    const list = buttons()
    const k = list.indexOf(document.activeElement as HTMLButtonElement)
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      e.stopPropagation()
      const step = e.key === 'ArrowDown' ? 1 : -1
      list[(k + step + list.length) % list.length]?.focus()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      if (onBack) onBack()
      else onClose()
    } else if (e.key === 'ArrowLeft' && onBack) {
      e.preventDefault()
      e.stopPropagation()
      onBack()
    } else if (e.key === 'ArrowRight') {
      const row = document.activeElement as HTMLElement | null
      const i = Number(row?.dataset.sub ?? NaN)
      if (row && Number.isFinite(i)) { e.preventDefault(); e.stopPropagation(); openAt(i, true, row) }
    }
  }

  return (
    <div ref={el} role="menu" aria-label={onBack ? undefined : 'Actions'} onKeyDown={keys} style={pos}
      className="fixed z-[60] min-w-[220px] rounded-md border border-zinc-700 bg-zinc-900 py-1 text-[12px] shadow-2xl">
      {rows.map((row, i) => {
        if (row === '-') return <div key={i} role="separator" className="my-1 border-t border-zinc-800" />
        if ('rows' in row) {
          return (
            <SideMenu key={row.label} index={i} label={row.label} rows={row.rows} state={state} at={open?.index === i ? open : null}
              onOpen={(byKey, el) => openAt(i, byKey, el)} onShut={() => setOpen(null)} onClose={onClose} run={run} />
          )
        }
        const cmd = command(row.id)
        const enabled = !cmd.enabled || cmd.enabled(state)
        return (
          <button key={row.id} type="button" role="menuitem" disabled={!enabled} onClick={() => run(cmd)}
            onPointerEnter={(e) => { setOpen(null); e.currentTarget.focus() }}
            className="flex w-full items-center justify-between gap-6 px-3 py-1 text-left text-zinc-200 outline-none hover:bg-emerald-600 hover:text-white focus:bg-emerald-600 focus:text-white disabled:text-zinc-600 disabled:hover:bg-transparent">
            <span>{row.label ?? cmd.label}</span>
            {cmd.keys && <kbd className="font-sans text-[11px] text-zinc-500">{cmd.keys}</kbd>}
          </button>
        )
      })}
    </div>
  )
}

function SideMenu({ index, label, rows, state, at, onOpen, onShut, onClose, run }: {
  index: number; label: string; rows: Row[]; state: State
  /** Out, at this point (`byKey`: opened by a key, so it takes the keyboard). */
  at: { x: number; y: number; back: number; byKey: boolean } | null
  onOpen: (byKey: boolean, row: HTMLElement) => void; onShut: () => void; onClose: () => void; run: (cmd: Command) => void
}) {
  const btn = useRef<HTMLButtonElement>(null)
  const open = !!at
  return (
    <>
      <button ref={btn} type="button" role="menuitem" aria-haspopup="menu" aria-expanded={open} data-sub={index}
        onClick={(e) => onOpen(true, e.currentTarget)} onPointerEnter={(e) => { e.currentTarget.focus(); onOpen(false, e.currentTarget) }}
        className={`flex w-full items-center justify-between gap-6 px-3 py-1 text-left outline-none focus:bg-emerald-600 focus:text-white ${open ? 'bg-zinc-800 text-white' : 'text-zinc-200 hover:bg-emerald-600 hover:text-white'}`}>
        <span>{label}</span><ChevronRight className="h-3.5 w-3.5 text-zinc-500" />
      </button>
      {at && (
        <Menu rows={rows} state={state} x={at.x} y={at.y} back={at.back} focus={at.byKey} onClose={onClose}
          onBack={() => { onShut(); btn.current?.focus() }} run={run} />
      )}
    </>
  )
}
