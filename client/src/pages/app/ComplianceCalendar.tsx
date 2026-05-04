import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Badge, Card, Select } from '../../components/ui'
import { CalendarDays, List, MapPin, AlertTriangle, ChevronLeft, ChevronRight, Loader2, Info, HelpCircle } from 'lucide-react'
import { fetchComplianceCalendar, fetchLocations, markAlertRead, dismissAlert } from '../../api/compliance'
import type { ComplianceCalendarItem } from '../../api/compliance'
import type { BusinessLocation } from '../../types/compliance'

type View = 'list' | 'month'

const STATUS_LABEL: Record<ComplianceCalendarItem['derived_status'], string> = {
  overdue: 'Overdue',
  due_soon: 'Due in 30 days',
  upcoming: 'Due in 90 days',
  future: 'Future',
}

const STATUS_HINT: Record<ComplianceCalendarItem['derived_status'], string> = {
  overdue: 'Past their deadline. Action needed.',
  due_soon: 'Deadline within 30 days. Schedule action this month.',
  upcoming: 'Deadline 31–90 days out. Plan ahead.',
  future: 'Deadline more than 90 days out. Awareness only.',
}

const STATUS_VARIANT: Record<
  ComplianceCalendarItem['derived_status'],
  'danger' | 'warning' | 'neutral' | 'success'
> = {
  overdue: 'danger',
  due_soon: 'warning',
  upcoming: 'neutral',
  future: 'success',
}

function formatDate(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatDays(d: number): string {
  if (d === 0) return 'today'
  if (d === 1) return 'tomorrow'
  if (d === -1) return '1 day overdue'
  if (d < 0) return `${Math.abs(d)} days overdue`
  return `in ${d} days`
}

export default function ComplianceCalendar() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const view: View = (searchParams.get('view') as View) || 'list'
  const locationFilter = searchParams.get('location') || ''
  const categoryFilter = searchParams.get('category') || ''

  const [items, setItems] = useState<ComplianceCalendarItem[]>([])
  const [locations, setLocations] = useState<BusinessLocation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    setError('')
    Promise.all([
      fetchComplianceCalendar({ location_id: locationFilter || undefined }),
      fetchLocations().catch(() => [] as BusinessLocation[]),
    ])
      .then(([cal, locs]) => {
        setItems(cal)
        setLocations(locs)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load calendar'))
      .finally(() => setLoading(false))
  }, [locationFilter])

  const categories = useMemo(() => {
    const set = new Set<string>()
    items.forEach((i) => {
      if (i.category) set.add(i.category)
    })
    return Array.from(set).sort()
  }, [items])

  const filtered = useMemo(() => {
    if (!categoryFilter) return items
    return items.filter((i) => i.category === categoryFilter)
  }, [items, categoryFilter])

  const grouped = useMemo(() => {
    const groups: Record<ComplianceCalendarItem['derived_status'], ComplianceCalendarItem[]> = {
      overdue: [],
      due_soon: [],
      upcoming: [],
      future: [],
    }
    filtered.forEach((i) => groups[i.derived_status].push(i))
    return groups
  }, [filtered])

  const setParam = (k: string, v: string) => {
    const next = new URLSearchParams(searchParams)
    if (v) next.set(k, v)
    else next.delete(k)
    setSearchParams(next, { replace: true })
  }

  const handleMarkRead = async (item: ComplianceCalendarItem) => {
    if (item.alert_status === 'read' || item.alert_status === 'actioned') return
    try {
      await markAlertRead(item.id)
      setItems((prev) =>
        prev.map((p) => (p.id === item.id ? { ...p, alert_status: 'read' } : p))
      )
    } catch {
      /* swallow — not critical */
    }
  }

  const handleDismiss = async (item: ComplianceCalendarItem) => {
    try {
      await dismissAlert(item.id)
      setItems((prev) => prev.filter((p) => p.id !== item.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to dismiss')
    }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold text-zinc-100">Compliance Calendar</h1>
            <HowItWorks />
          </div>
          <p className="text-sm text-zinc-500 mt-1">
            Filings, postings, and renewals across your locations.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setParam('view', 'list')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              view === 'list'
                ? 'bg-emerald-600 text-white'
                : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <List size={14} /> List
          </button>
          <button
            onClick={() => setParam('view', 'month')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              view === 'month'
                ? 'bg-emerald-600 text-white'
                : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <CalendarDays size={14} /> Month
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <Select
          label=""
          value={locationFilter}
          onChange={(e) => setParam('location', e.target.value)}
          placeholder="All locations"
          options={locations.map((l) => ({
            value: l.id,
            label: l.name || `${l.city || ''}, ${l.state || ''}`,
          }))}
        />
        <Select
          label=""
          value={categoryFilter}
          onChange={(e) => setParam('category', e.target.value)}
          placeholder="All categories"
          options={categories.map((c) => ({ value: c, label: c.replace(/_/g, ' ') }))}
        />
        {(locationFilter || categoryFilter) && (
          <button
            onClick={() => setSearchParams({}, { replace: true })}
            className="text-xs text-zinc-500 hover:text-zinc-300"
          >
            Clear filters
          </button>
        )}
      </div>

      {error && (
        <Card className="mb-4 border-red-900 bg-red-900/10">
          <div className="flex items-center gap-2 text-red-400 text-sm">
            <AlertTriangle size={14} /> {error}
          </div>
        </Card>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="animate-spin text-zinc-500" />
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <div className="text-center py-10 max-w-md mx-auto">
            <CalendarDays className="mx-auto text-zinc-600 mb-2" size={32} />
            <p className="text-sm text-zinc-400">No upcoming compliance deadlines.</p>
            <p className="text-xs text-zinc-600 mt-2 leading-relaxed">
              The calendar is populated from compliance alerts that include a deadline.
              Open <a href="/app/locations" className="text-emerald-400 hover:underline">Locations</a> and
              run a compliance check on a location — any rule changes or filings with a deadline
              will land here.
            </p>
          </div>
        </Card>
      ) : view === 'list' ? (
        <ListView
          grouped={grouped}
          onView={(item) => navigate(`/app/compliance?alert=${item.id}`)}
          onMarkRead={handleMarkRead}
          onDismiss={handleDismiss}
        />
      ) : (
        <MonthView items={filtered} onClick={(item) => navigate(`/app/compliance?alert=${item.id}`)} />
      )}
    </div>
  )
}

function HowItWorks() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-zinc-500 hover:text-zinc-300 p-1 rounded hover:bg-zinc-800"
        title="How this works"
      >
        <Info size={14} />
      </button>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" onClick={() => setOpen(false)}>
          <div
            className="bg-zinc-900 border border-zinc-700 rounded-xl max-w-md w-full p-5 space-y-4 text-sm text-zinc-300"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-zinc-100">How the calendar works</h3>
              <button onClick={() => setOpen(false)} className="text-zinc-500 hover:text-zinc-300">×</button>
            </div>
            <div className="space-y-3 text-xs leading-relaxed text-zinc-400">
              <div>
                <p className="text-zinc-300 font-medium mb-1">Where deadlines come from</p>
                Each row is a compliance alert with a deadline date. Alerts are
                generated when you run a compliance check on a location
                (Locations page → Run check). The system picks up rule changes
                from federal + state sources and turns any with a deadline into
                a calendar entry.
              </div>
              <div>
                <p className="text-zinc-300 font-medium mb-1">Status buckets</p>
                <ul className="space-y-1 list-disc list-inside">
                  <li><span className="text-red-400">Overdue</span> — past their deadline</li>
                  <li><span className="text-amber-400">Due in 30 days</span> — schedule action this month</li>
                  <li><span className="text-zinc-300">Due in 90 days</span> — plan ahead</li>
                  <li><span className="text-emerald-400">Future</span> — awareness only</li>
                </ul>
              </div>
              <div>
                <p className="text-zinc-300 font-medium mb-1">Per-row actions</p>
                <span className="text-zinc-300">Click a row</span> to mark it
                read. <span className="text-zinc-300">View</span> opens the
                full alert detail. <span className="text-zinc-300">Dismiss</span> removes
                it from the calendar (use this for false-positives or things
                you've already handled outside the system).
              </div>
              <div>
                <p className="text-zinc-300 font-medium mb-1">Filters</p>
                Location and category filters persist in the URL — bookmark a
                filtered view if you only care about, say, California payroll
                deadlines.
              </div>
              <div>
                <p className="text-zinc-300 font-medium mb-1">Coming soon</p>
                Email reminders 7 days before each deadline + iCal export.
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

interface ListViewProps {
  grouped: Record<ComplianceCalendarItem['derived_status'], ComplianceCalendarItem[]>
  onView: (item: ComplianceCalendarItem) => void
  onMarkRead: (item: ComplianceCalendarItem) => void
  onDismiss: (item: ComplianceCalendarItem) => void
}

function ListView({ grouped, onView, onMarkRead, onDismiss }: ListViewProps) {
  const order: ComplianceCalendarItem['derived_status'][] = ['overdue', 'due_soon', 'upcoming', 'future']
  return (
    <div className="space-y-6">
      {order.map((bucket) => {
        const rows = grouped[bucket]
        if (rows.length === 0) return null
        return (
          <section key={bucket}>
            <div className="flex items-center gap-2 mb-2">
              <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
                {STATUS_LABEL[bucket]}
              </h2>
              <span className="text-xs text-zinc-600">({rows.length})</span>
              <span className="text-xs text-zinc-600" title={STATUS_HINT[bucket]}>
                <HelpCircle size={11} className="inline opacity-60" />
              </span>
            </div>
            <div className="space-y-2">
              {rows.map((item) => (
                <Card
                  key={item.id}
                  className="hover:border-zinc-700 cursor-pointer transition-colors"
                >
                  <div className="flex items-start gap-3" onClick={() => onMarkRead(item)}>
                    <Badge variant={STATUS_VARIANT[bucket]}>
                      {formatDays(item.days_until_due)}
                    </Badge>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className={`text-sm font-medium ${
                            item.alert_status === 'unread' ? 'text-zinc-100' : 'text-zinc-300'
                          } truncate`}>
                            {item.title}
                          </p>
                          <div className="flex items-center gap-2 mt-1 text-xs text-zinc-500">
                            <span>{formatDate(item.deadline)}</span>
                            {item.location_name && (
                              <>
                                <span>·</span>
                                <span className="flex items-center gap-1">
                                  <MapPin size={10} />
                                  {item.location_name}
                                  {item.location_state ? `, ${item.location_state}` : ''}
                                </span>
                              </>
                            )}
                            {item.category && (
                              <>
                                <span>·</span>
                                <span>{item.category.replace(/_/g, ' ')}</span>
                              </>
                            )}
                          </div>
                          {item.action_required && (
                            <p className="text-xs text-zinc-400 mt-2 line-clamp-2">
                              {item.action_required}
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              onView(item)
                            }}
                            className="text-xs text-zinc-500 hover:text-zinc-200 px-2 py-1 rounded hover:bg-zinc-800"
                          >
                            View
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              onDismiss(item)
                            }}
                            className="text-xs text-zinc-500 hover:text-red-400 px-2 py-1 rounded hover:bg-zinc-800"
                          >
                            Dismiss
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}

interface MonthViewProps {
  items: ComplianceCalendarItem[]
  onClick: (item: ComplianceCalendarItem) => void
}

function MonthView({ items, onClick }: MonthViewProps) {
  const [cursor, setCursor] = useState(() => {
    const today = new Date()
    return new Date(today.getFullYear(), today.getMonth(), 1)
  })

  const monthLabel = cursor.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })

  const itemsByDate = useMemo(() => {
    const map = new Map<string, ComplianceCalendarItem[]>()
    items.forEach((i) => {
      const arr = map.get(i.deadline) ?? []
      arr.push(i)
      map.set(i.deadline, arr)
    })
    return map
  }, [items])

  const startOffset = cursor.getDay()
  const daysInMonth = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate()
  const today = new Date()
  const todayKey = today.toISOString().slice(0, 10)

  const cells = []
  for (let i = 0; i < startOffset; i++) cells.push(null)
  for (let day = 1; day <= daysInMonth; day++) {
    const d = new Date(cursor.getFullYear(), cursor.getMonth(), day)
    const key = d.toISOString().slice(0, 10)
    cells.push({ day, key, items: itemsByDate.get(key) ?? [] })
  }

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}
          className="p-1 rounded hover:bg-zinc-800 text-zinc-400"
        >
          <ChevronLeft size={18} />
        </button>
        <h2 className="text-sm font-semibold text-zinc-100">{monthLabel}</h2>
        <button
          onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}
          className="p-1 rounded hover:bg-zinc-800 text-zinc-400"
        >
          <ChevronRight size={18} />
        </button>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-[10px] uppercase text-zinc-600 mb-1">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
          <div key={d}>{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((cell, i) =>
          cell === null ? (
            <div key={`empty-${i}`} />
          ) : (
            <div
              key={cell.key}
              className={`min-h-[64px] p-1 rounded border text-xs ${
                cell.key === todayKey
                  ? 'border-emerald-700 bg-emerald-900/10'
                  : 'border-zinc-800 bg-zinc-900/50'
              }`}
            >
              <div className="text-[10px] text-zinc-500 mb-1">{cell.day}</div>
              <div className="space-y-0.5">
                {cell.items.slice(0, 3).map((it) => (
                  <button
                    key={it.id}
                    onClick={() => onClick(it)}
                    className={`w-full text-left truncate px-1 py-0.5 rounded text-[10px] ${
                      it.derived_status === 'overdue'
                        ? 'bg-red-900/40 text-red-300'
                        : it.derived_status === 'due_soon'
                          ? 'bg-amber-900/40 text-amber-300'
                          : 'bg-zinc-800 text-zinc-300'
                    }`}
                  >
                    {it.title}
                  </button>
                ))}
                {cell.items.length > 3 && (
                  <p className="text-[10px] text-zinc-600 px-1">+{cell.items.length - 3} more</p>
                )}
              </div>
            </div>
          )
        )}
      </div>
    </Card>
  )
}
