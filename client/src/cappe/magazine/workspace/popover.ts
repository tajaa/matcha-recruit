// The workspace's popovers: a panel opened under the control that opens it.

import { useEffect, useRef, useState } from 'react'

/** A popover kept on screen, placed by its anchor when opened, closed by a
 *  click outside it or Escape. `size`: the room it needs (the colour
 *  picker's, unless said). */
export function usePopover(anchor: React.RefObject<HTMLElement | null>, size: { w: number; h: number } = { w: 248, h: 330 }) {
  const panel = useRef<HTMLDivElement>(null)
  const [at, setAt] = useState<{ left: number; top: number } | null>(null)
  const open = at !== null
  const toggle = () => {
    if (open || !anchor.current) { setAt(null); return }
    const r = anchor.current.getBoundingClientRect()
    const { w, h } = size
    setAt({ left: Math.max(8, Math.min(window.innerWidth - w - 8, r.right - w)), top: r.bottom + h > window.innerHeight ? Math.max(8, r.top - h - 4) : r.bottom + 4 })
  }
  useEffect(() => {
    if (!open) return
    const down = (e: PointerEvent) => {
      if (panel.current?.contains(e.target as Node) || anchor.current?.contains(e.target as Node)) return
      setAt(null)
    }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setAt(null) }
    window.addEventListener('pointerdown', down, true)
    window.addEventListener('keydown', key)
    return () => { window.removeEventListener('pointerdown', down, true); window.removeEventListener('keydown', key) }
  }, [open, anchor])
  return { panel, at, toggle }
}
