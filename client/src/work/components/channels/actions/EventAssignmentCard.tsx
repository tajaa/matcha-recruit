import { Check, ClipboardCheck, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { completeEventAssignment, getEventAssignment, type EmsEventAssignment } from '../../../api/events'

interface EventAssignmentCardProps {
  action: NonNullable<NonNullable<import('../../../api/channels').ChannelMessage['metadata']>['action']>
}

export default function EventAssignmentCard({ action }: EventAssignmentCardProps) {
  const [assignment, setAssignment] = useState<EmsEventAssignment | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    getEventAssignment(action.id)
      .then((data) => { if (active) setAssignment(data) })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : 'Assignment is unavailable.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [action.id])

  useEffect(() => {
    if (!assignment || !action.status) return
    if (action.status === assignment.status || action.status === assignment.event_status) return
    setAssignment((current) => {
      if (!current) return current
      switch (action.status) {
        case 'completed':
          return { ...current, status: 'completed' }
        case 'cancelled':
          return { ...current, status: 'cancelled' }
        case 'promoted':
        case 'dismissed':
          return { ...current, event_status: action.status }
        default:
          return current
      }
    })
  }, [action.status, assignment])

  async function complete() {
    setBusy(true)
    setError(null)
    try {
      const updated = await completeEventAssignment(action.id)
      setAssignment(updated)
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'Assignment could not be completed.')
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <div className="mt-2 text-[11px] text-w-dim">Loading assignment…</div>
  if (!assignment) return error ? <div className="mt-2 text-[11px] text-red-300">{error}</div> : null

  const eventClosed = assignment.event_status !== 'logged'
  const stateLabel = eventClosed
    ? assignment.event_status === 'promoted' ? 'Event promoted' : assignment.event_status === 'dismissed' ? 'Event closed — no action' : `Event ${assignment.event_status}`
    : assignment.status === 'completed' ? 'Assignment completed' : assignment.status === 'cancelled' ? 'Assignment cancelled' : 'Assignment open'

  return (
    <div className="mt-2 w-full max-w-sm rounded-lg border border-w-line bg-w-surface2/60 p-2.5 text-left">
      <div className="flex items-center gap-1.5 text-[11px] font-medium text-w-text">
        <ClipboardCheck size={13} className="text-w-accent" />
        Event assignment
      </div>
      <div className="mt-1 text-[11px] font-medium text-w-text">{assignment.shared_title}</div>
      <div className="mt-1 text-[11px] text-w-dim">Assigned to {assignment.assignee_name}</div>
      {assignment.instructions && <div className="mt-1 text-[11px] text-w-dim whitespace-pre-wrap">{assignment.instructions}</div>}
      {assignment.due_at && <div className="mt-1 text-[10px] text-w-faint">Due {new Date(assignment.due_at).toLocaleString()}</div>}
      <div className="mt-2 flex items-center gap-2">
        <span className={`text-[10px] ${eventClosed || assignment.status !== 'assigned' ? 'text-w-dim' : 'text-amber-300'}`}>{stateLabel}</span>
        {assignment.can_view_event && <a href={`/work/events/${assignment.event_id}`} className="ml-auto text-[10px] text-w-accent hover:underline">View event</a>}
        {assignment.can_complete && assignment.status === 'assigned' && !eventClosed && (
          <button
            type="button"
            disabled={busy}
            onClick={complete}
            className="ml-auto inline-flex items-center gap-1 rounded bg-w-accent px-2 py-1 text-[11px] font-medium text-black disabled:opacity-50"
          >
            {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
            Mark complete
          </button>
        )}
      </div>
      {error && <div className="mt-1 text-[11px] text-red-300">{error}</div>}
    </div>
  )
}
