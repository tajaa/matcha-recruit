import { useCallback, useEffect, useId, useRef, useState, type CSSProperties, type FocusEvent } from 'react'
import { createPortal } from 'react-dom'
import { Check, ChevronDown } from 'lucide-react'

type Option = { value: string; label: string }

type SelectProps = {
  label?: string
  options: Option[]
  value?: string
  onChange?: (event: { target: { value: string } }) => void
  onBlur?: () => void
  placeholder?: string
  id?: string
  className?: string
  disabled?: boolean
  name?: string
  required?: boolean
  autoFocus?: boolean
  /**
   * Render the open list in a portal on <body>, fixed-positioned against the
   * trigger. Use it inside a scroll container (a Modal body with
   * `overflow-y-auto`): an absolutely-positioned list is clipped by that
   * container, where a native <select> popup never was. Off by default so every
   * other call site keeps the simpler in-flow list.
   */
  portal?: boolean
}

const PANEL_MAX_HEIGHT = 280
const PANEL_GAP = 4

export function Select({
  label,
  options,
  value = '',
  onChange,
  onBlur,
  placeholder,
  id,
  className = '',
  disabled = false,
  name,
  required,
  autoFocus,
  portal = false,
}: SelectProps) {
  const [open, setOpen] = useState(false)
  const [placement, setPlacement] = useState<CSSProperties | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  // See Input: an unassociated label is a caption, not a label. `||`, not `??`:
  // an empty-string id associates nothing either.
  const generated = useId()
  const selectId = id || generated

  const all: Option[] = placeholder
    ? [{ value: '', label: placeholder }, ...options]
    : options
  const selected = all.find((o) => o.value === value) ?? all[0]

  // Fixed coordinates for the portaled list: below the trigger, or above it
  // when there is more room there.
  const place = useCallback(() => {
    const anchor = ref.current
    if (!anchor) return
    const rect = anchor.getBoundingClientRect()
    const below = window.innerHeight - rect.bottom - PANEL_GAP
    const above = rect.top - PANEL_GAP
    const flip = below < PANEL_MAX_HEIGHT && above > below
    setPlacement({
      position: 'fixed',
      left: rect.left,
      width: rect.width,
      maxHeight: Math.max(120, Math.min(PANEL_MAX_HEIGHT, flip ? above : below)),
      ...(flip ? { bottom: window.innerHeight - rect.top + PANEL_GAP } : { top: rect.bottom + PANEL_GAP }),
    })
  }, [])

  useEffect(() => {
    if (!open) return
    function onClick(e: MouseEvent) {
      const target = e.target as Node
      if (ref.current?.contains(target) || panelRef.current?.contains(target)) return
      setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key !== 'Escape') return
      if (portal) triggerRef.current?.focus()  // before the list unmounts under it
      setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    // A portaled list is pinned to viewport coordinates, so it follows the
    // trigger when anything scrolls (capture: a scrolling modal body doesn't
    // bubble its scroll to window) or the window resizes.
    if (portal) {
      window.addEventListener('scroll', place, true)
      window.addEventListener('resize', place)
    }
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [open, portal, place])

  // A portaled list lives at the end of <body>, so Tab from the trigger would
  // skip straight past it — a keyboard user could open it and never reach an
  // option. Move focus in on open (the selected option, else the first).
  useEffect(() => {
    if (!open || !portal) return
    const panel = panelRef.current
    const target = panel?.querySelector<HTMLElement>('[data-selected]') ?? panel?.querySelector<HTMLElement>('button')
    target?.focus()
  }, [open, portal])

  function toggle() {
    if (disabled) return
    if (!open && portal) place()
    setOpen((v) => !v)
  }

  function pick(v: string) {
    if (portal) triggerRef.current?.focus()
    setOpen(false)
    onChange?.({ target: { value: v } })
  }

  function handleBlur(event: FocusEvent<HTMLDivElement>) {
    const next = event.relatedTarget
    // A portaled list sits outside this wrapper in the DOM but inside it in
    // React's tree (its focus events bubble here), so check both.
    if (next instanceof Node && (event.currentTarget.contains(next) || panelRef.current?.contains(next))) return
    // Focus left both the trigger and the list: a detached, fixed list must not
    // linger over the page.
    if (portal) setOpen(false)
    onBlur?.()
  }

  const skin = 'bg-zinc-900 border border-white/10 rounded-lg shadow-2xl shadow-black/40 overflow-hidden overflow-y-auto'
  const list = (
    <div
      ref={panelRef}
      className={portal ? `z-[60] ${skin}` : `absolute left-0 right-0 top-full mt-1 z-50 max-h-[280px] ${skin}`}
      style={portal ? placement ?? undefined : undefined}
    >
      {all.map((opt) => {
        const isSel = opt.value === selected?.value
        return (
          <button
            key={opt.value}
            type="button"
            data-selected={isSel || undefined}
            onClick={() => pick(opt.value)}
            className={`w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-[12px] transition-colors ${
              isSel ? 'text-zinc-100 bg-white/[0.04]' : 'text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.03]'
            }`}
          >
            <span className="truncate">{opt.label}</span>
            {isSel && <Check className="w-3 h-3 text-emerald-400 shrink-0" strokeWidth={2} />}
          </button>
        )
      })}
    </div>
  )

  return (
    <div className={className}>
      {label && (
        <label htmlFor={selectId} className="block text-[10px] font-medium uppercase tracking-[0.16em] text-zinc-500 mb-1.5">
          {label}{required && <span className="text-red-400 ml-1">*</span>}
        </label>
      )}
      <div ref={ref} className="relative" onBlur={handleBlur}>
        <button
          ref={triggerRef}
          type="button"
          id={selectId}
          name={name}
          disabled={disabled}
          autoFocus={autoFocus}
          onClick={toggle}
          className={`w-full flex items-center justify-between gap-2 bg-zinc-900 border border-white/[0.08] rounded-lg px-3 py-2 text-[12px] text-zinc-200 hover:border-white/15 hover:bg-zinc-800/60 transition-colors ${
            disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
          } ${open ? 'border-white/20' : ''}`}
        >
          <span className="truncate">{selected?.label ?? placeholder ?? ''}</span>
          <ChevronDown className={`w-3.5 h-3.5 text-zinc-500 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} strokeWidth={1.6} />
        </button>
        {open && (portal ? (placement ? createPortal(list, document.body) : null) : list)}
      </div>
    </div>
  )
}
