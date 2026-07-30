import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ClipboardList, Loader2 } from 'lucide-react'
import { useMe } from '../../hooks/useMe'
import { useToast } from '../../components/ui'
import { ApiError } from '../../api/client'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import { canReviewEvents } from '../utils/eventsPermissions'
import { EMS_CATEGORY_LABELS, getEvent, listEvents, updateEvent, type EmsEvent } from '../api/events'
import { EventList } from '../components/events/EventList'
import { EventDetail } from '../components/events/EventDetail'
import { PromoteModal } from '../components/events/PromoteModal'

type StatusFilter = 'all' | 'logged' | 'promoted' | 'dismissed'

const STATUS_TABS: { key: StatusFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'logged', label: 'Logged' },
  { key: 'promoted', label: 'Promoted' },
  { key: 'dismissed', label: 'Dismissed' },
]

export default function EventsHub() {
  const { eventId } = useParams<{ eventId: string }>()
  const navigate = useNavigate()
  const base = useWorkBase()
  const { me, hasFeature } = useMe()
  const { toast } = useToast()
  const canReview = canReviewEvents(me?.user?.role)
  const hasIncidents = hasFeature('incidents')

  const [events, setEvents] = useState<EmsEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [selectedEvent, setSelectedEvent] = useState<EmsEvent | null>(null)
  const [mobileShowDetail, setMobileShowDetail] = useState(false)
  const [showPromote, setShowPromote] = useState(false)

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

  async function handleDismiss() {
    if (!selectedEvent) return
    try {
      const updated = await updateEvent(selectedEvent.id, { dismissed: true })
      applyEventUpdate(updated)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast('This event was already promoted or dismissed.', 'error')
        loadEvents()
      } else {
        toast(err instanceof Error ? err.message : 'Failed to dismiss event', 'error')
      }
    }
  }

  function handlePromoted(incidentId: string) {
    if (selectedEvent) {
      applyEventUpdate({ ...selectedEvent, status: 'promoted', incident_id: incidentId })
    }
    setShowPromote(false)
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
              canReview={canReview}
              hasIncidents={hasIncidents}
              onDismiss={handleDismiss}
              onPromote={() => setShowPromote(true)}
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
    </div>
  )
}
