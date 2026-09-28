import { useState } from 'react'
import { ChevronLeft, ChevronRight, Info, RotateCcw } from 'lucide-react'
import { fetchBreakReminderEvents, fetchBreakReminderFilterOptions } from '../../api/employees/employeeSchedule'
import { DataTable, type Column } from '../ui'
import { useAsync } from '../../hooks/useAsync'
import { formatDay, formatOccurredAt, reminderText } from './breakReminderFormat'
import type {
  BreakReminderEvent,
  BreakReminderEventsResponse,
  BreakReminderFilterOptions,
  BreakReminderFilters,
  BreakReminderOutcome,
} from '../../types/employeeSchedule'
import { errorMessage } from '../../types/employeeSchedule'

const PAGE_SIZE = 50
const inputClass = 'w-full rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-2 text-sm text-zinc-200 outline-none focus:border-zinc-500'

type FilterState = { locationId: string; employeeId: string; start: string; end: string }

const EMPTY_FILTERS: FilterState = { locationId: '', employeeId: '', start: '', end: '' }
const EMPTY_OPTIONS: BreakReminderFilterOptions = { locations: [], employees: [] }
const EMPTY_PAGE: BreakReminderEventsResponse = { events: [], total: 0 }

const OUTCOME: Record<BreakReminderOutcome, { label: string; className: string }> = {
  accepted: { label: 'Accepted by provider', className: 'border-emerald-800/60 bg-emerald-950/40 text-emerald-300' },
  failed: { label: 'Failed', className: 'border-red-900/60 bg-red-950/40 text-red-300' },
  unavailable: { label: 'Unavailable', className: 'border-zinc-700 bg-zinc-900 text-zinc-400' },
}

function apiFilters(filters: FilterState, offset: number): BreakReminderFilters {
  return {
    locationId: filters.locationId || undefined,
    employeeId: filters.employeeId || undefined,
    start: filters.start || undefined,
    end: filters.end || undefined,
    limit: PAGE_SIZE,
    offset,
  }
}

function recipientText(event: BreakReminderEvent): string {
  if (event.recipient_type === 'manager') return 'Supervisor'
  return event.employee?.name || 'Unnamed employee'
}

function optionName(options: Array<{ id: string; name: string | null }>, id: string, fallback: string): string {
  return options.find((option) => option.id === id)?.name || fallback
}

export default function BreakReminderDeliveryLog() {
  const [draft, setDraft] = useState<FilterState>(EMPTY_FILTERS)
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS)
  const [offset, setOffset] = useState(0)
  const [rangeError, setRangeError] = useState<string | null>(null)

  // The history still loads unfiltered if options fail; the selects offer "All".
  const { data: options } = useAsync(
    () => fetchBreakReminderFilterOptions().catch(() => EMPTY_OPTIONS),
    [],
    EMPTY_OPTIONS,
  )
  const page = useAsync(
    () => fetchBreakReminderEvents(apiFilters(filters, offset)).catch((reason: unknown) => {
      throw new Error(errorMessage(reason))
    }),
    [filters, offset],
    EMPTY_PAGE,
  )
  const loading = page.loading
  // A failed reload keeps the last rows in useAsync; under new filters those rows
  // would describe a different query, so an error shows alone.
  const error = page.error
  const events = error ? [] : page.data.events
  const total = error ? 0 : page.data.total

  function applyFilters(event: React.FormEvent) {
    event.preventDefault()
    if (draft.start && draft.end && draft.end < draft.start) {
      setRangeError('The "To" date must be on or after the "From" date.')
      return
    }
    setRangeError(null)
    setOffset(0)
    setFilters(draft)
  }

  function resetFilters() {
    setRangeError(null)
    setDraft(EMPTY_FILTERS)
    setFilters(EMPTY_FILTERS)
    setOffset(0)
  }

  const activeFilters = [
    filters.locationId && `Location: ${optionName(options.locations, filters.locationId, 'Selected location')}`,
    filters.employeeId && `Employee: ${optionName(options.employees, filters.employeeId, 'Selected employee')}`,
    (filters.start || filters.end) && `Dates: ${filters.start ? formatDay(filters.start) : 'Any'} – ${filters.end ? formatDay(filters.end) : 'Any'} (inclusive)`,
  ].filter(Boolean) as string[]

  const columns: Column<BreakReminderEvent>[] = [
    { key: 'when', header: 'Sent (location time)', className: 'whitespace-nowrap', render: formatOccurredAt },
    { key: 'channel', header: 'Channel', render: (event) => event.channel === 'push' ? 'Push' : 'Email' },
    { key: 'reminder', header: 'Reminder', render: reminderText },
    {
      key: 'recipient', header: 'Recipient',
      render: (event) => <div><div>{recipientText(event)}</div>{event.recipient && <div className="text-xs text-zinc-500">{event.recipient}</div>}</div>,
    },
    { key: 'location', header: 'Location', render: (event) => event.location?.name || '—' },
    {
      key: 'outcome', header: 'Delivery status',
      render: (event) => <span className={`inline-flex whitespace-nowrap rounded-full border px-2 py-0.5 text-xs ${OUTCOME[event.outcome].className}`}>{OUTCOME[event.outcome].label}</span>,
    },
    { key: 'detail', header: 'Provider detail', className: 'text-xs text-zinc-400', render: (event) => event.outcome_detail || 'No details reported' },
  ]

  const pageStart = total === 0 ? 0 : offset + 1
  const pageEnd = Math.min(offset + PAGE_SIZE, total)

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-medium text-zinc-100">Break reminder deliveries</h2>
        <p className="mt-1 text-sm text-zinc-500">Every meal and rest break reminder Matcha attempted by email or push, with what the provider reported at the time.</p>
      </div>

      <div role="note" className="flex gap-2 rounded-lg border border-amber-900/50 bg-amber-950/20 px-3 py-2.5 text-xs text-amber-200/90">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          These records show delivery attempts only. <b>Accepted by provider</b> means the email or push service took the message — not that the employee received or read it, and not that a break was taken. Break compliance is shown by time records, not by reminders. <b>Unavailable</b> means no message could be sent (for example, no registered device).
        </p>
      </div>

      <form onSubmit={applyFilters} className="grid gap-3 rounded-xl border border-zinc-800 bg-zinc-900/30 p-4 md:grid-cols-2 xl:grid-cols-4">
        <Filter label="Location">
          <select value={draft.locationId} onChange={(event) => setDraft({ ...draft, locationId: event.target.value })} className={inputClass}>
            <option value="">All locations</option>
            {options.locations.map((location) => <option key={location.id} value={location.id}>{location.name || 'Unnamed location'}</option>)}
          </select>
        </Filter>
        <Filter label="Employee">
          <select value={draft.employeeId} onChange={(event) => setDraft({ ...draft, employeeId: event.target.value })} className={inputClass}>
            <option value="">All employees</option>
            {options.employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.name || 'Unnamed employee'}</option>)}
          </select>
        </Filter>
        <Filter label="From"><input type="date" value={draft.start} onChange={(event) => setDraft({ ...draft, start: event.target.value })} className={inputClass} /></Filter>
        <Filter label="To (inclusive)"><input type="date" value={draft.end} onChange={(event) => setDraft({ ...draft, end: event.target.value })} className={inputClass} /></Filter>
        <div className="flex flex-wrap items-center gap-2 md:col-span-2 xl:col-span-4">
          <button type="submit" className="rounded-lg bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white">Apply filters</button>
          <button type="button" onClick={resetFilters} className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:text-zinc-100"><RotateCcw className="h-3.5 w-3.5" /> Reset</button>
          {rangeError && <span role="alert" className="text-xs text-red-400">{rangeError}</span>}
        </div>
      </form>

      <p className="text-xs text-zinc-500" aria-live="polite">
        {activeFilters.length ? `Filtered by ${activeFilters.join(' · ')}` : 'Showing all locations, employees and dates.'} Dates are each location's calendar day.
      </p>

      <DataTable
        columns={columns}
        rows={events}
        rowKey={(event) => event.id}
        loading={loading}
        loadingText="Loading delivery history..."
        error={error}
        emptyText={activeFilters.length ? 'No break reminder deliveries match these filters.' : 'No break reminders have been sent yet.'}
      />

      <div className="flex items-center justify-between gap-3 text-xs text-zinc-500">
        <span>{total ? `Showing ${pageStart}–${pageEnd} of ${total}` : 'No entries'}</span>
        <div className="flex gap-2">
          <button type="button" onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} disabled={offset === 0 || loading} className="rounded-lg border border-zinc-800 p-1.5 hover:text-zinc-200 disabled:opacity-40" aria-label="Previous delivery page"><ChevronLeft className="h-4 w-4" /></button>
          <button type="button" onClick={() => setOffset(offset + PAGE_SIZE)} disabled={offset + PAGE_SIZE >= total || loading} className="rounded-lg border border-zinc-800 p-1.5 hover:text-zinc-200 disabled:opacity-40" aria-label="Next delivery page"><ChevronRight className="h-4 w-4" /></button>
        </div>
      </div>
    </div>
  )
}

function Filter({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="space-y-1.5"><span className="text-xs font-medium text-zinc-500">{label}</span>{children}</label>
}
