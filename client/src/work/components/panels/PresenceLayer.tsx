import { useEffect, useRef, useState } from 'react'
import RemoteCursorView from './RemoteCursor'
import type { PresenceMember } from '../../api/projectSocket'
import type { RemoteCursor } from '../../hooks/useProjectPresence'

interface Props {
  members: PresenceMember[]
  remoteCursors: Map<string, RemoteCursor>
  reportCursor: (xPct: number, yPct: number) => void
  selfId?: string
  pageKey: string  // only render cursors when on a sub-tab where they're tracked
  children: React.ReactNode
  /**
   * Only fire mousemove + render cursors when active. Allows the parent
   * (ProjectView) to disable presence on tabs we don't track (Pipeline /
   * Chat) without unmounting.
   */
  enabled?: boolean
}

/**
 * Wraps the active project sub-tab. Captures local mousemove → reports xPct/yPct
 * (relative to its own bounding rect). Renders RemoteCursorView for each
 * remote user the hook says is on the same page_key.
 *
 * Renders an absolute overlay with `pointer-events: none` so cursor visuals
 * don't interfere with clicks/selection in the underlying surface.
 */
export default function PresenceLayer({
  members,
  remoteCursors,
  reportCursor,
  selfId,
  pageKey,
  children,
  enabled = true,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })

  // Track container size so the overlay can map xPct → px on render.
  useEffect(() => {
    if (!enabled) return
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect
      if (rect) setSize({ w: rect.width, h: rect.height })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [enabled])

  // Initial size sync.
  useEffect(() => {
    const el = containerRef.current
    if (el) {
      const rect = el.getBoundingClientRect()
      setSize({ w: rect.width, h: rect.height })
    }
  }, [enabled, pageKey])

  function onMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    if (!enabled) return
    const el = containerRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) return
    const xPct = (e.clientX - rect.left) / rect.width
    const yPct = (e.clientY - rect.top) / rect.height
    if (xPct < 0 || xPct > 1 || yPct < 0 || yPct > 1) return
    reportCursor(xPct, yPct)
  }

  // Build a name lookup for cursor labels.
  const memberById = new Map(members.map((m) => [m.id, m]))

  return (
    <div
      ref={containerRef}
      onMouseMove={onMouseMove}
      style={{ position: 'relative', width: '100%', height: '100%' }}
    >
      {children}
      {enabled && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            pointerEvents: 'none',
            overflow: 'hidden',
          }}
        >
          {Array.from(remoteCursors.entries()).map(([userId, cursor]) => {
            if (userId === selfId) return null
            const m = memberById.get(userId)
            if (!m || m.page_key !== pageKey) return null
            return (
              <RemoteCursorView
                key={userId}
                userId={userId}
                name={m.name}
                cursor={cursor}
                containerWidth={size.w}
                containerHeight={size.h}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}
