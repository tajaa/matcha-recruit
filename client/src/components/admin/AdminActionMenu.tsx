import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { MoreHorizontal } from 'lucide-react'
import { AdminButton } from './AdminUI'

type Action = { label: string; onSelect?: () => void; to?: string; href?: string; disabled?: boolean; danger?: boolean }

/** Portaled so row actions stay compact without being clipped by a scrolling table. */
export function AdminActionMenu({ label, items }: { label: string; items: readonly Action[] }) {
  const id = useId()
  const trigger = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null)

  function open() {
    const rect = trigger.current?.getBoundingClientRect()
    if (!rect) return
    const height = Math.min(items.length * 32 + 8, 320)
    setPosition({
      left: Math.max(8, Math.min(rect.right - 208, window.innerWidth - 216)),
      top: rect.bottom + height + 8 < window.innerHeight ? rect.bottom + 4 : Math.max(8, rect.top - height - 4),
    })
  }

  useEffect(() => {
    if (!position) return
    menu.current?.querySelector<HTMLElement>('[role="menuitem"]:not([disabled])')?.focus()
    const outside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) setPosition(null)
    }
    const scroll = (event: Event) => { if (!(event.target instanceof Node) || !menu.current?.contains(event.target)) setPosition(null) }
    const resize = () => setPosition(null)
    document.addEventListener('pointerdown', outside)
    window.addEventListener('scroll', scroll, true)
    window.addEventListener('resize', resize)
    return () => {
      document.removeEventListener('pointerdown', outside)
      window.removeEventListener('scroll', scroll, true)
      window.removeEventListener('resize', resize)
    }
  }, [position])

  return <>
    <AdminButton ref={trigger} aria-label={label} title={label} aria-haspopup="menu" aria-expanded={!!position} aria-controls={position ? id : undefined} variant="ghost" className="p-1.5!" onClick={() => position ? setPosition(null) : open()} onKeyDown={(event) => {
      if (event.key === 'ArrowDown') { event.preventDefault(); open() }
    }}><MoreHorizontal size={16} /></AdminButton>
    {position && createPortal(<div ref={menu} id={id} role="menu" aria-label={label} style={position} className="admin-popover fixed z-40 max-h-80 w-52 max-w-[calc(100vw-16px)] overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-900 p-1 shadow-xl" onKeyDown={(event) => {
      const entries = Array.from(menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])') ?? [])
      const index = entries.indexOf(document.activeElement as HTMLElement)
      if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault()
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? entries.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + entries.length) % entries.length
        entries[next]?.focus()
      } else if (event.key === 'Escape' || event.key === 'Tab') {
        if (event.key === 'Escape') event.preventDefault()
        setPosition(null)
        trigger.current?.focus()
      }
    }}>
      {items.map((item) => {
        const className = `flex w-full items-center rounded px-3 py-2 text-left text-xs outline-none hover:bg-zinc-800 focus:bg-zinc-800 disabled:opacity-40 ${item.danger ? 'text-red-300' : 'text-zinc-200'}`
        if (item.to) return <Link key={item.label} role="menuitem" tabIndex={-1} to={item.to} className={className} onClick={() => setPosition(null)}>{item.label}</Link>
        if (item.href) return <a key={item.label} role="menuitem" tabIndex={-1} href={item.href} target="_blank" rel="noopener noreferrer" className={className} onClick={() => setPosition(null)}>{item.label}</a>
        return <button key={item.label} type="button" role="menuitem" tabIndex={-1} disabled={item.disabled} className={className} onClick={() => { setPosition(null); item.onSelect?.() }}>{item.label}</button>
      })}
    </div>, document.body)}
  </>
}
