import { AdminButton, AdminInput, AdminSelect } from '../../../components/admin/AdminUI'
import { useState } from 'react'
import { Copy, Check } from 'lucide-react'
import { useAsync } from '../../../hooks/useAsync'
import { useDebounced } from '../../../hooks/useDebounced'
import { api } from '../../../api/client'
import { ErrorConsole, ErrorTimeFilter } from '../../../components/admin/ErrorConsole'

type Kind =
  | 'exception'
  | 'http_error'
  | 'db_error'
  | 'background_task'
  | 'celery_task'
  | 'startup'
  | 'warning'
  | 'unhandled'

type Source = 'api' | 'celery' | 'worker' | 'startup'

interface ErrorItem {
  id: string
  fingerprint: string
  kind: Kind
  level: string
  logger_name: string | null
  message: string
  exception_type: string | null
  traceback: string | null
  source: Source
  hostname: string | null
  request_method: string | null
  request_path: string | null
  request_status: number | null
  user_id: string | null
  user_email: string | null
  context: Record<string, unknown> | null
  occurrences: number
  first_seen: string | null
  last_seen: string | null
  resolved_at: string | null
}

interface ListResponse {
  total: number
  items: ErrorItem[]
}

interface StatsResponse {
  by_kind: { kind: Kind; count: number; occurrences: number }[]
  by_source: { source: Source; count: number; occurrences: number }[]
  top: {
    id: string
    message: string
    kind: Kind
    exception_type: string | null
    occurrences: number
    last_seen: string | null
  }[]
}

const KIND_LABEL: Record<Kind, string> = {
  exception: 'Exception',
  http_error: 'HTTP 5xx',
  db_error: 'DB Error',
  background_task: 'Background',
  celery_task: 'Celery',
  startup: 'Startup',
  warning: 'Warning',
  unhandled: 'Unhandled',
}

const KIND_COLOR: Record<Kind, string> = {
  exception: 'bg-red-500/15 text-red-300 border-red-500/30',
  http_error: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  db_error: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
  background_task: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  celery_task: 'bg-teal-500/15 text-teal-300 border-teal-500/30',
  startup: 'bg-pink-500/15 text-pink-300 border-pink-500/30',
  warning: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  unhandled: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
}

const ALL_KINDS: Kind[] = [
  'exception',
  'http_error',
  'db_error',
  'celery_task',
  'background_task',
  'startup',
  'unhandled',
  'warning',
]

function formatErrorReport(item: ErrorItem): string {
  const request = [item.request_method, item.request_path].filter(Boolean).join(' ')
  const details = [
    'Matcha server error report',
    `Error ID: ${item.id}`,
    `Exception: ${item.exception_type || '—'}`,
    `Message: ${item.message}`,
    `Kind: ${KIND_LABEL[item.kind]} (${item.kind})`,
    `Level: ${item.level}`,
    `Source: ${item.source}`,
    item.request_status != null ? `HTTP status: ${item.request_status}` : null,
    request ? `Request: ${request}` : null,
    item.logger_name ? `Logger: ${item.logger_name}` : null,
    item.hostname ? `Host: ${item.hostname}` : null,
    item.user_id ? `User ID: ${item.user_id}` : null,
    item.user_email ? `User email: ${item.user_email}` : null,
    `Occurrences: ${item.occurrences}`,
    item.first_seen ? `First seen: ${item.first_seen}` : null,
    item.last_seen ? `Last seen: ${item.last_seen}` : null,
    `Fingerprint: ${item.fingerprint}`,
  ].filter((detail): detail is string => Boolean(detail))

  if (item.context && Object.keys(item.context).length > 0) {
    details.push(`\nContext:\n${JSON.stringify(item.context, null, 2)}`)
  }
  if (item.traceback) {
    details.push(`\nTraceback:\n${item.traceback}`)
  }

  return details.join('\n')
}

export default function ServerErrors() {
  const [kindFilter, setKindFilter] = useState<Kind | ''>('')
  const [sourceFilter, setSourceFilter] = useState<Source | ''>('')
  const [showResolved, setShowResolved] = useState(false)
  const [searchFilter, setSearchFilter] = useState('')
  const [sinceHours, setSinceHours] = useState(24)
  // The search box refetches, so debounce the TRIGGER — otherwise typing
  // "database" fires eight list+stats request pairs at the admin API.
  const debouncedSearch = useDebounced(searchFilter)

  const [copied, setCopied] = useState<string | null>(null)

  const { data, loading, error, reload: refresh } = useAsync(
    async () => {
      const params = new URLSearchParams()
      if (kindFilter) params.set('kind', kindFilter)
      if (sourceFilter) params.set('source', sourceFilter)
      if (searchFilter) params.set('search', searchFilter)
      params.set('resolved', String(showResolved))
      params.set('since_hours', String(sinceHours))
      params.set('limit', '100')

      const [listRes, statsRes] = await Promise.all([
        api.get<ListResponse>(`/admin/server-errors?${params.toString()}`),
        api.get<StatsResponse>(`/admin/server-errors/stats?since_hours=${sinceHours}`),
      ])
      return { items: listRes.items, total: listRes.total, stats: statsRes }
    },
    [kindFilter, sourceFilter, debouncedSearch, showResolved, sinceHours],
    { items: [] as ErrorItem[], total: 0, stats: null as StatsResponse | null },
  )
  const { items, total, stats } = data

  async function copyErrorReport(item: ErrorItem) {
    try {
      await navigator.clipboard.writeText(formatErrorReport(item))
      setCopied(item.id)
      setTimeout(() => setCopied(null), 1500)
    } catch (error) {
      console.error('Could not copy server error report', error)
    }
  }

  async function resolve(id: string) {
    try {
      await api.post(`/admin/server-errors/${id}/resolve`, {})
      refresh()
    } catch (e) {
      console.error(e)
    }
  }

  async function unresolve(id: string) {
    try {
      await api.post(`/admin/server-errors/${id}/unresolve`, {})
      refresh()
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <ErrorConsole
      title="Server errors"
      description={<>Backend exceptions, HTTP 5xx, database errors, and tasks — last {sinceHours} hours ({total} total).</>}
      loading={loading}
      error={error ? `Couldn’t load server errors: ${error}` : null}
      onRefresh={refresh}
      kinds={ALL_KINDS.map((key) => ({ key, label: KIND_LABEL[key], color: KIND_COLOR[key], count: stats?.by_kind.find((row) => row.kind === key)?.occurrences ?? 0 }))}
      selectedKind={kindFilter}
      onKindChange={(value) => setKindFilter(value as Kind | '')}
      filters={<>
        <AdminInput aria-label="Search error message" value={searchFilter} onChange={(event) => setSearchFilter(event.target.value)} placeholder="Search message…" className="max-w-xs" />
        <AdminSelect aria-label="Error source" value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value as Source | '')}>
          <option value="">All sources</option><option value="api">API</option><option value="celery">Celery</option><option value="worker">Worker</option><option value="startup">Startup</option>
        </AdminSelect>
        <ErrorTimeFilter value={sinceHours} onChange={setSinceHours} />
        <label className="flex items-center gap-2 text-sm text-zinc-300"><input type="checkbox" checked={showResolved} onChange={(event) => setShowResolved(event.target.checked)} />Show resolved</label>
      </>}
      items={items}
      summary={(item) => ({
        id: item.id, kind: item.kind, at: item.last_seen, email: item.user_email, status: item.request_status, resolved: !!item.resolved_at,
        title: <>{item.exception_type && <span className="font-mono text-red-300">{item.exception_type}: </span>}{item.message}</>,
        subtitle: <>{item.request_method ? `${item.request_method} ` : ''}{item.request_path || item.logger_name}</>,
        badges: <><span>{item.source}</span>{item.occurrences > 1 && <span className="text-amber-400">{item.occurrences}×</span>}</>,
      })}
      details={(item) => ({
        trace: item.traceback ? { label: 'Traceback', value: item.traceback } : undefined,
        context: item.context,
        fields: [{ label: 'First seen', value: item.first_seen }, { label: 'Host', value: item.hostname || '—' }, { label: 'Fingerprint', value: item.fingerprint }],
        actions: <><AdminButton variant="ghost" onClick={() => copyErrorReport(item)} title="Copy the error message, request details, context, and traceback">{copied === item.id ? <Check size={12} /> : <Copy size={12} />}{copied === item.id ? 'Copied' : 'Copy report'}</AdminButton><AdminButton variant={item.resolved_at ? 'secondary' : 'success'} onClick={() => item.resolved_at ? unresolve(item.id) : resolve(item.id)}>{item.resolved_at ? 'Mark unresolved' : 'Mark resolved'}</AdminButton></>,
      })}
      top={(stats?.top ?? []).map((item) => ({ id: item.id, kind: item.kind, count: item.occurrences, title: <>{item.exception_type && <span className="text-red-300">{item.exception_type}: </span>}{item.message}</>, at: item.last_seen }))}
    />
  )
}
