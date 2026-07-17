import { Info } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

const GAP = 8 // px between trigger and bubble
const EDGE = 8 // min px from a viewport edge
const CLOSE_GRACE_MS = 120

/**
 * Hover bubble that renders into document.body rather than next to its trigger.
 *
 * The portal is the whole point, and it fixes two separate bugs that the old
 * `absolute`-positioned bubble had:
 *
 *  1. CLIPPING. Every card on this page is `rounded-* overflow-hidden` (the
 *     overflow is what clips the cell backgrounds to the rounded corners), and
 *     an absolutely-positioned child cannot escape an ancestor's overflow —
 *     no z-index defeats it. The bubble was cut off at the card edge.
 *  2. INHERITED TEXT TRANSFORM. The triggers live inside `uppercase
 *     tracking-widest` labels, and CSS inheritance follows the DOM, so a
 *     bubble nested in that label rendered its prose AS SHOUTY WIDE CAPS.
 *     Portalled content is not a DOM descendant, so it inherits nothing (the
 *     explicit normal-case/tracking-normal below is belt-and-braces).
 *
 * Positioning is therefore viewport-relative (`fixed`): prefer above the
 * trigger, flip below when there isn't room, and clamp horizontally so the
 * bubble stays on screen at any window size. Recomputed on scroll/resize
 * because fixed elements don't travel with the page.
 */
export function HoverTip({
  text,
  children,
  className = '',
}: {
  text: string
  children: React.ReactNode
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const triggerRef = useRef<HTMLSpanElement>(null)
  const tipRef = useRef<HTMLDivElement>(null)
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const cancelClose = useCallback(() => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current)
      closeTimer.current = null
    }
  }, [])

  // Grace period so the cursor can travel across the gap onto the bubble
  // without it vanishing — the bubble keeps itself open via its own
  // onMouseEnter, which is only reachable because it isn't pointer-events-none.
  const scheduleClose = useCallback(() => {
    cancelClose()
    closeTimer.current = setTimeout(() => setOpen(false), CLOSE_GRACE_MS)
  }, [cancelClose])

  useLayoutEffect(() => {
    if (!open) {
      setPos(null)
      return
    }
    const place = () => {
      const trigger = triggerRef.current?.getBoundingClientRect()
      const tip = tipRef.current
      if (!trigger || !tip) return
      const { offsetHeight: h, offsetWidth: w } = tip

      const above = trigger.top - GAP - h
      const top = above >= EDGE ? above : trigger.bottom + GAP
      const centred = trigger.left + trigger.width / 2 - w / 2
      const left = Math.min(Math.max(EDGE, centred), Math.max(EDGE, window.innerWidth - w - EDGE))
      setPos({ top, left })
    }
    place()
    // capture:true — an ancestor scroll container moves the trigger too.
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [open])

  useEffect(() => cancelClose, [cancelClose])

  return (
    <span
      ref={triggerRef}
      className={`inline-flex ${className}`}
      onMouseEnter={() => {
        cancelClose()
        setOpen(true)
      }}
      onMouseLeave={scheduleClose}
    >
      {children}
      {open &&
        createPortal(
          <div
            ref={tipRef}
            role="tooltip"
            onMouseEnter={cancelClose}
            onMouseLeave={scheduleClose}
            style={{
              top: pos?.top ?? 0,
              left: pos?.left ?? 0,
              // Rendered once unpositioned so it can be measured; keep that
              // first frame invisible rather than flashing at the origin.
              visibility: pos ? 'visible' : 'hidden',
            }}
            className="fixed z-[100] w-56 max-w-[calc(100vw-16px)] px-3 py-2 text-[11px] leading-relaxed text-zinc-200 bg-zinc-900 border border-white/10 rounded-lg shadow-2xl text-left normal-case tracking-normal font-normal"
          >
            {text}
          </div>,
          document.body,
        )}
    </span>
  )
}

export function InfoTip({ text }: { text: string }) {
  return (
    <HoverTip text={text} className="ml-1 cursor-help">
      <Info size={11} className="text-zinc-600 hover:text-zinc-400 transition-colors" />
    </HoverTip>
  )
}
