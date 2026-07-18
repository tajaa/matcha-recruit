import { useEffect, useRef } from 'react'
import { Loader2 } from 'lucide-react'
import type { EnrichEvent } from '../../../hooks/admin/useEnrichStream'
import { eventStyle, eventText } from './helpers'

export default function EventFeed({ events, running, label }: { events: EnrichEvent[]; running: boolean; label: string }) {
  const feedRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: 'smooth' })
  }, [events])
  if (!events.length && !running) return null
  return (
    <div ref={feedRef} className="rounded-xl border border-vsc-border bg-vsc-panel p-4 max-h-72 overflow-y-auto space-y-2">
      {events.filter((e) => e.type !== 'complete').map((ev, i) => {
        const { icon: Icon, color, spin } = eventStyle(ev.type)
        return (
          <div key={i} className="flex items-start gap-3 text-sm">
            <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${color} ${spin ? 'animate-pulse' : ''}`} />
            <div className="flex-1 min-w-0">
              <span className="text-zinc-300">{eventText(ev)}</span>
              {ev.type === 'roles_detected' && ev.roles && ev.roles.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {ev.roles.map((r) => (
                    <span key={r} className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20">{r}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )
      })}
      {running && (
        <div className="flex items-center gap-2 text-xs text-zinc-500 pt-1">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> {label}
        </div>
      )}
    </div>
  )
}
