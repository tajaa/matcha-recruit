import { useEffect, useRef, useState } from 'react'
import { Bell, X } from 'lucide-react'
import { relativeTime } from '../../../../utils/format'
import type { MWNotification } from '../../../api/notifications'
import { NEEDS_YOU, UPDATE_LABEL } from './hrCaseGuide'

type Props = {
  items: MWNotification[]
  unread: number
  onOpen: (n: MWNotification) => void
  onMarkAllRead: () => void
}

/** The page's own notice feed: HR-case notices only, newest first. */
export default function HrCaseUpdates({ items, unread, onOpen, onMarkAllRead }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="true"
        className="relative inline-flex items-center gap-1.5 rounded-lg border border-w-line px-2.5 py-1.5 text-xs text-w-dim transition-colors hover:bg-w-surface2 hover:text-w-text"
      >
        <Bell size={14} />
        Updates
        {unread > 0 && (
          <span className="ml-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-bold text-white" aria-label={`${unread} unread`}>
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="fixed inset-x-3 top-24 z-40 overflow-hidden rounded-xl border border-w-line bg-w-surface shadow-2xl sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:w-96">
          <div className="flex items-center justify-between border-b border-w-line px-4 py-3">
            <span className="text-xs font-medium text-w-text">HR case updates</span>
            <div className="flex items-center gap-3">
              {unread > 0 && <button type="button" onClick={onMarkAllRead} className="text-[11px] text-w-accent hover:underline">Mark all read</button>}
              <button type="button" onClick={() => setOpen(false)} className="text-w-dim hover:text-w-text" aria-label="Close updates"><X size={14} /></button>
            </div>
          </div>
          <div className="max-h-[60vh] overflow-y-auto">
            {items.length === 0 ? (
              <p className="px-4 py-8 text-center text-xs leading-5 text-w-dim">
                No updates yet. You’ll see a notice here when a case is flagged, a write-up comes in, or a signed copy needs a look.
              </p>
            ) : items.map((n) => (
              <button
                key={n.id}
                type="button"
                onClick={() => { setOpen(false); onOpen(n) }}
                className={`block w-full border-b border-w-line/50 px-4 py-3 text-left transition-colors hover:bg-w-surface2/50 ${n.is_read ? '' : 'bg-w-surface2/30'}`}
              >
                <div className="flex items-center gap-2">
                  {!n.is_read && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-w-accent" aria-label="Unread" />}
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${NEEDS_YOU.has(n.type) ? 'bg-amber-500/15 text-amber-300' : 'bg-w-surface2 text-w-dim'}`}>
                    {UPDATE_LABEL[n.type] ?? 'Update'}
                  </span>
                  <span className="ml-auto text-[10px] text-w-faint">{relativeTime(n.created_at)}</span>
                </div>
                <p className={`mt-1.5 text-xs ${n.is_read ? 'text-w-dim' : 'font-medium text-w-text'}`}>{n.title}</p>
                {n.body && <p className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-w-dim">{n.body}</p>}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
