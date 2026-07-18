import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Card, Select } from '../../../components/ui'
import { CalendarDays, List, AlertTriangle, Loader2 } from 'lucide-react'
import { fetchComplianceCalendar, fetchLocations, markAlertRead, dismissAlert } from '../../../api/compliance/compliance'
import type { ComplianceCalendarItem } from '../../../api/compliance/compliance'
import type { BusinessLocation } from '../../../types/compliance'
import type { View } from './ComplianceCalendar/types'
import { HowItWorks } from './ComplianceCalendar/HowItWorks'
import { ListView } from './ComplianceCalendar/ListView'
import { MonthView } from './ComplianceCalendar/MonthView'

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
    // Baseline rows have synthetic ids prefixed `baseline:` and aren't
    // backed by the alerts table — there's nothing to mark.
    if (item.alert_status === 'baseline' || item.id.startsWith('baseline:')) return
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
    if (item.alert_status === 'baseline' || item.id.startsWith('baseline:')) return
    try {
      await dismissAlert(item.id)
      setItems((prev) => prev.filter((p) => p.id !== item.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to dismiss')
    }
  }

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-6 gap-4">
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
