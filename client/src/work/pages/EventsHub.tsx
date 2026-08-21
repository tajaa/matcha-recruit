import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ClipboardList, Loader2 } from 'lucide-react'
import { useMe } from '../../hooks/useMe'
import { useToast } from '../../components/ui'
import { ApiError } from '../../api/client'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import { canAssignEvents, canPromoteEvents, canResolveEvents, canReviewEvents } from '../utils/eventsPermissions'
import { EMS_CATEGORY_LABELS, getEvent, listEvents, resolveEvent, type EmsEvent } from '../api/events'
import { EventList } from '../components/events/EventList'
import { EventDetail } from '../components/events/EventDetail'
import { PromoteModal } from '../components/events/PromoteModal'
import EventAssignmentModal from '../components/events/EventAssignmentModal'

type StatusFilter = 'all' | 'logged' | 'completed' | 'promoted' | 'dismissed'

const STATUS_TABS: { key: StatusFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'logged', label: 'Logged' },
  { key: 'completed', label: 'Completed' },
  { key: 'promoted', label: 'Promoted' },
  { key: 'dismissed', label: 'No action' },
]

export default function EventsHub() {
  const { eventId } = useParams<{ eventId: string }>()
  const navigate = useNavigate()
  const base = useWorkBase()
  const { me, loading: meLoading, hasFeature } = useMe()
  const { toast } = useToast()
  const opsAccess = me?.ops_access ?? me?.work_access
  const canReview = canReviewEvents(opsAccess)
  const canResolve = canResolveEvents(opsAccess)
  const canPromote = canPromoteEvents(opsAccess)
  const canAssign = canAssignEvents(opsAccess)
  const hasIncidents = hasFeature('incidents')

  const [events, setEvents] = useState<EmsEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [selectedEvent, setSelectedEvent] = useState<EmsEvent | null>(null)
  const [mobileShowDetail, setMobileShowDetail] = useState(false)
  const [showPromote, setShowPromote] = useState(false)
  const [showAssign, setShowAssign] = useState(false)

  const loadEvents = useCallback(async () => {
    setLoading(true)
    try {
      const { events: rows } = await listEvents({
        status: statusFilter === 'all' ? undefined : statusFilter,
        category: categoryFilter === 'all' ? undefined : categoryFilter,
      })
      setEvents(rows)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load events')
    } finally {
      setLoading(false)
    }
  }, [statusFilter, categoryFilter])

  useEffect(() => {
    loadEvents()
  }, [loadEvents])

  // Deep-link support: /events/:eventId may name an event outside the
  // currently-loaded filter window, so fetch it directly rather than relying
  // on the list to already contain it.
  useEffect(() => {
    if (!eventId) return
    const inList = events.find((e) => e.id === eventId)
    if (inList) {
      setSelectedEvent(inList)
      setMobileShowDetail(true)
      return
    }
    getEvent(eventId)
      .then((event) => {
        setSelectedEvent(event)
        setMobileShowDetail(true)
      })
      .catch(() => {})
  }, [eventId, events])

  function handleSelect(event: EmsEvent) {
    setSelectedEvent(event)
    setMobileShowDetail(true)
    navigate(`${base}/events/${event.id}`)
  }

  function handleMobileBack() {
    setMobileShowDetail(false)
    navigate(`${base}/events`)
  }

  function applyEventUpdate(updated: EmsEvent) {
    // Reconcile against the active status filter: a dismissed/promoted
    // event must leave the Logged list immediately, not sit there with a
    // stale banner until the next full reload. The detail pane keeps
    // showing the updated event (status banner) even after its row leaves
    // the list.
    setEvents((prev) =>
      statusFilter !== 'all' && updated.status !== statusFilter
        ? prev.filter((e) => e.id !== updated.id)
        : prev.map((e) => (e.id === updated.id ? updated : e)),
    )
    setSelectedEvent((prev) => (prev && prev.id === updated.id ? updated : prev))
  }

  async function handleResolve(resolution: 'completed' | 'no_action') {
    if (!selectedEvent) return
    try {
      const updated = await resolveEvent(selectedEvent.id, { resolution })
      applyEventUpdate(updated)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast('This event was already resolved or promoted.', 'error')
        loadEvents()
      } else {
        toast(err instanceof Error ? err.message : 'Failed to resolve event', 'error')
      }
    }
  }

  function handlePromoted(incidentId: string) {
    if (selectedEvent) {
      applyEventUpdate({ ...selectedEvent, status: 'promoted', incident_id: incidentId })
    }
    setShowPromote(false)
  }

  // meLoading first: canReviewEvents(undefined) reads as "no permission"
  // before /auth/me resolves, so checking !canReview before meLoading
  // flashed the denial stub on every hard reload of /work/events.
  if (meLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-5 h-5 text-w-dim animate-spin" />
      </div>
    )
  }

  if (!canReview) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-w-dim">
        You don't have permission to review events.
      </div>
    )
  }

  return (
    <div className="h-[calc(100vh-64px)] flex">
      {/* Left panel: filters + list */}
      <div
        className={`w-full md:w-96 md:shrink-0 border-r border-w-line bg-w-bg ${
          mobileShowDetail ? 'hidden md:flex md:flex-col' : 'flex flex-col'
        }`}
      >
        <div className="px-4 pt-4 pb-3 border-b border-w-line">
          <h1 className="text-lg font-semibold text-w-text mb-3">Events</h1>

          <div className="flex gap-1 rounded-lg bg-w-surface p-1 mb-2">
            {STATUS_TABS.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setStatusFilter(tab.key)}
                className={`flex-1 rounded-md px-2 py-1.5 text-xs font-medium transition-colors ${
                  statusFilter === tab.key ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-w-text'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="w-full rounded-lg border border-w-line bg-w-surface px-2.5 py-1.5 text-xs text-w-text outline-none focus:border-w-accent/50 transition-colors"
          >
            <option value="all">All categories</option>
            {Object.entries(EMS_CATEGORY_LABELS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>

        {loading ? (
          <div className="flex items-center justify-center flex-1">
            <Loader2 className="w-5 h-5 text-w-dim animate-spin" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center flex-1 gap-2 px-4 text-center">
            <p className="text-sm text-red-400">{error}</p>
            <button onClick={loadEvents} className="text-sm text-w-dim hover:text-w-text transition-colors">
              Try again
            </button>
          </div>
        ) : (
          <EventList events={events} selectedId={selectedEvent?.id ?? null} onSelect={handleSelect} />
        )}
      </div>

      {/* Right panel: detail */}
      <div
        className={`flex-1 bg-w-bg ${mobileShowDetail ? 'flex flex-col' : 'hidden md:flex md:flex-col'}`}
      >
        {selectedEvent ? (
          <>
            <div className="md:hidden px-4 py-2 border-b border-w-line">
              <button onClick={handleMobileBack} className="text-sm text-w-dim hover:text-w-text transition-colors">
                ← Back
              </button>
            </div>
            <EventDetail
              event={selectedEvent}
              canResolve={canResolve}
              canPromote={canPromote && hasIncidents && selectedEvent.source_kind !== 'schedule_compliance_warning'}
              canAssign={canAssign}
              onResolve={handleResolve}
              onPromote={() => setShowPromote(true)}
              onAssign={() => setShowAssign(true)}
            />
          </>
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <ClipboardList className="w-10 h-10 text-w-faint" />
            <p className="text-sm text-w-dim">Select an event</p>
          </div>
        )}
      </div>

      {showPromote && selectedEvent && (
        <PromoteModal event={selectedEvent} onClose={() => setShowPromote(false)} onPromoted={handlePromoted} />
      )}
      {showAssign && selectedEvent && (
        <EventAssignmentModal
          event={selectedEvent}
          onClose={() => setShowAssign(false)}
          onCreated={() => {
            setShowAssign(false)
            toast('Event assigned to the channel.', 'success')
          }}
        />
      )}
    </div>
  )
}
