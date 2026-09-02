import { useCallback, useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Download, Eye, Loader2, RotateCcw } from 'lucide-react'
import { exportScheduleAuditLogs, fetchScheduleAuditLogs } from '../../api/employees/employeeSchedule'
import { DataTable, Modal, useToast, type Column } from '../ui'
import type {
  ScheduleAuditAction,
  ScheduleAuditEntry,
  ScheduleAuditFilters,
} from '../../types/employeeSchedule'
import { errorMessage } from '../../types/employeeSchedule'

const PAGE_SIZE = 50
const inputClass = 'w-full rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-2 text-sm text-zinc-200 outline-none focus:border-zinc-500'

const ACTION_LABEL: Record<ScheduleAuditAction, string> = {
  'shift.update': 'Shift updated',
  'shift.delete': 'Shift deleted',
  'assignment.create': 'Employee assigned',
  'assignment.delete': 'Employee unassigned',
}

type FilterState = {
  start: string
  end: string
  shiftId: string
  actorUserId: string
  employeeId: string
}

const EMPTY_FILTERS: FilterState = {
  start: '',
  end: '',
  shiftId: '',
  actorUserId: '',
  employeeId: '',
}

function apiFilters(filters: FilterState, offset = 0): ScheduleAuditFilters {
  return {
    start: filters.start ? `${filters.start}T00:00:00` : undefined,
    end: filters.end ? `${filters.end}T00:00:00` : undefined,
    shiftId: filters.shiftId.trim() || undefined,
    actorUserId: filters.actorUserId || undefined,
    employeeId: filters.employeeId.trim() || undefined,
    limit: PAGE_SIZE,
    offset,
  }
}

function personName(entry: ScheduleAuditEntry): string {
  return entry.modifying_user.name || entry.modifying_user.email || 'System'
}

function employeeNames(entry: ScheduleAuditEntry): string {
  if (entry.assigned_employees.length === 0) return '—'
  return entry.assigned_employees.map((employee) => employee.name || employee.id).join(', ')
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  return Number.isNaN(date.getTime()) ? timestamp : date.toLocaleString()
}

function displayValue(value: unknown): string {
  if (value == null || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  return JSON.stringify(value, null, 2)
}

export default function ScheduleAuditLog() {
  const { toast } = useToast()
  const [draftFilters, setDraftFilters] = useState<FilterState>(EMPTY_FILTERS)
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS)
  const [offset, setOffset] = useState(0)
  const [entries, setEntries] = useState<ScheduleAuditEntry[]>([])
  const [knownActors, setKnownActors] = useState<Map<string, string>>(new Map())
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<ScheduleAuditEntry | null>(null)
  const [action, setAction] = useState<ScheduleAuditAction | ''>('')
  const [exporting, setExporting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetchScheduleAuditLogs(apiFilters(filters, offset))
      setEntries(response.logs)
      setTotal(response.total)
      setKnownActors((current) => {
        const next = new Map(current)
        for (const entry of response.logs) {
          if (entry.modifying_user.id) next.set(entry.modifying_user.id, personName(entry))
        }
        return next
      })
    } catch (reason) {
      setEntries([])
      setTotal(0)
      setError(errorMessage(reason))
    } finally {
      setLoading(false)
    }
  }, [filters, offset])

  useEffect(() => { void load() }, [load])

  const visibleEntries = useMemo(
    () => action ? entries.filter((entry) => entry.action === action) : entries,
    [action, entries],
  )

  const columns: Column<ScheduleAuditEntry>[] = [
    { key: 'when', header: 'When', className: 'whitespace-nowrap', render: (entry) => formatTimestamp(entry.timestamp) },
    { key: 'action', header: 'Change', className: 'whitespace-nowrap', render: (entry) => ACTION_LABEL[entry.action] },
    { key: 'actor', header: 'Changed by', render: personName },
    { key: 'employees', header: 'Employees', render: employeeNames },
    { key: 'fields', header: 'Fields', render: (entry) => entry.fields.length ? entry.fields.join(', ') : '—' },
    { key: 'shift', header: 'Shift', className: 'font-mono text-xs text-zinc-500', render: (entry) => entry.shift_id || '—' },
    { key: 'inspect', header: '', align: 'right', render: (entry) => <button type="button" onClick={(event) => { event.stopPropagation(); setSelected(entry) }} className="inline-flex items-center gap-1 text-xs text-emerald-300 hover:text-emerald-200"><Eye className="h-3.5 w-3.5" /> Inspect</button> },
  ]

  function applyFilters(event: React.FormEvent) {
    event.preventDefault()
    if (draftFilters.start && draftFilters.end && draftFilters.end <= draftFilters.start) {
      toast('End date must be after start date.', 'error')
      return
    }
    setOffset(0)
    setFilters(draftFilters)
  }

  function resetFilters() {
    setDraftFilters(EMPTY_FILTERS)
    setFilters(EMPTY_FILTERS)
    setAction('')
    setOffset(0)
  }

  async function exportCsv() {
    setExporting(true)
    try {
      const { limit: _limit, offset: _offset, ...serverFilters } = apiFilters(filters)
      await exportScheduleAuditLogs(serverFilters)
    } catch (reason) {
      toast(errorMessage(reason), 'error')
    } finally {
      setExporting(false)
    }
  }

  const pageStart = total === 0 ? 0 : offset + 1
  const pageEnd = Math.min(offset + PAGE_SIZE, total)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-medium text-zinc-100">Published shift history</h2>
          <p className="mt-1 text-sm text-zinc-500">Review manager changes made after a shift was published. Employee swap and pickup requests are excluded.</p>
        </div>
        <button type="button" onClick={() => void exportCsv()} disabled={exporting} className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:border-zinc-600 hover:text-zinc-100 disabled:opacity-50">
          {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />} Export CSV
        </button>
      </div>

      <form onSubmit={applyFilters} className="grid gap-3 rounded-xl border border-zinc-800 bg-zinc-900/30 p-4 md:grid-cols-2 xl:grid-cols-6">
        <Filter label="From"><input type="date" value={draftFilters.start} onChange={(event) => setDraftFilters({ ...draftFilters, start: event.target.value })} className={inputClass} /></Filter>
        <Filter label="To (exclusive)"><input type="date" value={draftFilters.end} onChange={(event) => setDraftFilters({ ...draftFilters, end: event.target.value })} className={inputClass} /></Filter>
        <Filter label="Changed by">
          <select value={draftFilters.actorUserId} onChange={(event) => setDraftFilters({ ...draftFilters, actorUserId: event.target.value })} className={inputClass}>
            <option value="">All users</option>
            {[...knownActors].sort((a, b) => a[1].localeCompare(b[1])).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        </Filter>
        <Filter label="Action">
          <select value={action} onChange={(event) => setAction(event.target.value as ScheduleAuditAction | '')} className={inputClass}>
            <option value="">All actions</option>
            {(Object.entries(ACTION_LABEL) as Array<[ScheduleAuditAction, string]>).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </Filter>
        <Filter label="Shift ID"><input value={draftFilters.shiftId} onChange={(event) => setDraftFilters({ ...draftFilters, shiftId: event.target.value })} placeholder="UUID" className={inputClass} /></Filter>
        <Filter label="Employee ID"><input value={draftFilters.employeeId} onChange={(event) => setDraftFilters({ ...draftFilters, employeeId: event.target.value })} placeholder="UUID" className={inputClass} /></Filter>
        <div className="flex items-end gap-2 md:col-span-2 xl:col-span-6">
          <button type="submit" className="rounded-lg bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white">Apply filters</button>
          <button type="button" onClick={resetFilters} className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:text-zinc-100"><RotateCcw className="h-3.5 w-3.5" /> Reset</button>
          {action && <span className="text-xs text-zinc-500">Action applies to this page; CSV export includes all actions matching the other filters.</span>}
        </div>
      </form>

      <DataTable columns={columns} rows={visibleEntries} rowKey={(entry) => entry.id} loading={loading} loadingText="Loading audit history..." error={error} emptyText={action && entries.length > 0 ? 'No matching actions on this page.' : 'No published-shift changes match these filters.'} onRowClick={setSelected} />

      <div className="flex items-center justify-between gap-3 text-xs text-zinc-500">
        <span>{total ? `Showing ${pageStart}–${pageEnd} of ${total}` : 'No entries'}</span>
        <div className="flex gap-2">
          <button type="button" onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} disabled={offset === 0 || loading} className="rounded-lg border border-zinc-800 p-1.5 hover:text-zinc-200 disabled:opacity-40" aria-label="Previous audit page"><ChevronLeft className="h-4 w-4" /></button>
          <button type="button" onClick={() => setOffset(offset + PAGE_SIZE)} disabled={offset + PAGE_SIZE >= total || loading} className="rounded-lg border border-zinc-800 p-1.5 hover:text-zinc-200 disabled:opacity-40" aria-label="Next audit page"><ChevronRight className="h-4 w-4" /></button>
        </div>
      </div>

      <AuditDetail entry={selected} onClose={() => setSelected(null)} />
    </div>
  )
}

function Filter({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="space-y-1.5"><span className="text-xs font-medium text-zinc-500">{label}</span>{children}</label>
}

function AuditDetail({ entry, onClose }: { entry: ScheduleAuditEntry | null; onClose: () => void }) {
  return (
    <Modal open={entry != null} onClose={onClose} title={entry ? ACTION_LABEL[entry.action] : 'Audit entry'} width="xl">
      {entry && <div className="max-h-[70vh] space-y-5 overflow-y-auto pr-1">
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <Detail label="When" value={formatTimestamp(entry.timestamp)} />
          <Detail label="Changed by" value={personName(entry)} />
          <Detail label="Shift ID" value={entry.shift_id || '—'} mono />
          <Detail label="Employees" value={employeeNames(entry)} />
        </dl>
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">Changed fields</h3>
          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-zinc-950/50 text-zinc-500"><tr><th className="px-3 py-2 font-medium">Field</th><th className="px-3 py-2 font-medium">Before</th><th className="px-3 py-2 font-medium">After</th></tr></thead>
              <tbody className="divide-y divide-zinc-800 text-zinc-300">
                {entry.fields.map((field) => <tr key={field}><td className="px-3 py-2 font-mono text-xs text-zinc-400">{field}</td><td className="max-w-xs whitespace-pre-wrap break-words px-3 py-2">{displayValue(entry.before?.[field] ?? (field === 'assignment' ? entry.before : null))}</td><td className="max-w-xs whitespace-pre-wrap break-words px-3 py-2">{displayValue(entry.after?.[field] ?? (field === 'assignment' ? entry.after : null))}</td></tr>)}
                {entry.fields.length === 0 && <tr><td colSpan={3} className="px-3 py-4 text-zinc-500">No field-level diff was recorded.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
        <details className="rounded-lg border border-zinc-800 p-3">
          <summary className="cursor-pointer text-xs font-medium text-zinc-400">Raw audit details</summary>
          <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words text-xs text-zinc-500">{JSON.stringify(entry.details, null, 2)}</pre>
        </details>
        <div className="flex justify-end"><button type="button" onClick={onClose} className="rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:text-zinc-100">Close</button></div>
      </div>}
    </Modal>
  )
}

function Detail({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div><dt className="text-xs text-zinc-500">{label}</dt><dd className={`mt-1 break-words text-zinc-200 ${mono ? 'font-mono text-xs' : ''}`}>{value}</dd></div>
}
