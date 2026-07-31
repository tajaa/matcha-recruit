import { AlertTriangle, ClipboardList } from 'lucide-react'
import { EMS_CATEGORY_LABELS, type EmsEvent } from '../../api/events'

interface EventListProps {
  events: EmsEvent[]
  selectedId: string | null
  onSelect: (event: EmsEvent) => void
}

function statusDotClass(status: EmsEvent['status']): string {
  if (status === 'promoted') return 'bg-emerald-400'
  if (status === 'dismissed') return 'bg-w-faint'
  return 'bg-w-accent'
}

export function EventList({ events, selectedId, onSelect }: EventListProps) {
  if (events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 px-6 text-center">
        <ClipboardList className="w-10 h-10 text-w-faint" />
        <div>
          <p className="text-sm text-w-dim">No events yet</p>
          <p className="text-xs text-w-faint mt-1">
            Type "@huume ..." in a channel to log one.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto">
      {events.map((event) => {
        const isSelected = event.id === selectedId
        const label = event.title || event.narrative.slice(0, 80)
        return (
          <button
            key={event.id}
            onClick={() => onSelect(event)}
            className={`w-full text-left px-4 py-3 border-b border-w-line/60 transition-colors ${
              isSelected ? 'bg-w-surface2' : 'hover:bg-w-surface2/50'
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${statusDotClass(event.status)}`} />
              <span className="text-[10px] uppercase tracking-[0.12em] text-w-dim font-medium">
                {EMS_CATEGORY_LABELS[event.category]}
              </span>
              {event.urgency && event.status === 'logged' && (
                <AlertTriangle className="w-3 h-3 text-red-500 shrink-0" />
              )}
              {!event.urgency && event.incident_recommendation && event.status === 'logged' && (
                <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0" />
              )}
              <span className="ml-auto text-[10px] text-w-faint shrink-0">
                {new Date(event.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' })}
              </span>
            </div>
            <p className="text-sm text-w-text truncate">{label}</p>
            <p className="text-xs text-w-faint truncate mt-0.5">
              {event.channel_name ? `#${event.channel_name}` : 'Unknown channel'}
              {event.reporter_name ? ` · ${event.reporter_name}` : ''}
            </p>
          </button>
        )
      })}
    </div>
  )
}
