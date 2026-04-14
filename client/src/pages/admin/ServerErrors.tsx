import { useEffect, useState, useCallback } from 'react'
import { AlertTriangle, RefreshCw, Search, ChevronDown, ChevronRight, Copy, Check } from 'lucide-react'
import { api } from '../../api/client'

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

function relTime(iso: string | null): string {
  if (!iso) return '—'
  const ms = Date.now() - new Date(iso).getTime()
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

export default function ServerErrors() {
  const [items, setItems] = useState<ErrorItem[]>([])
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [kindFilter, setKindFilter] = useState<Kind | ''>('')
  const [sourceFilter, setSourceFilter] = useState<Source | ''>('')
  const [showResolved, setShowResolved] = useState(false)
  const [searchFilter, setSearchFilter] = useState('')
  const [sinceHours, setSinceHours] = useState(24)
  const [total, setTotal] = useState(0)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [copied, setCopied] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
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
      setItems(listRes.items)
      setTotal(listRes.total)
      setStats(statsRes)
    } catch (err) {
      console.error('Failed to load server errors', err)
    } finally {
      setLoading(false)
    }
  }, [kindFilter, sourceFilter, searchFilter, showResolved, sinceHours])

  useEffect(() => {
    refresh()
  }, [refresh])

  function toggleExpand(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function copyText(text: string, id: string) {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(id)
      setTimeout(() => setCopied(null), 1500)
    } catch {}
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
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="flex items-center gap-2">
            <AlertTriangle size={20} className="text-red-500" />
            <h1 className="text-xl font-semibold text-zinc-100">Server Errors</h1>
          </div>
          <p className="text-sm text-zinc-500 mt-0.5">
            Backend errors — exceptions, HTTP 5xx, DB, Celery tasks — last {sinceHours} hours ({total} total)
          </p>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800 text-zinc-200 text-xs font-medium hover:bg-zinc-700 disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
          {ALL_KINDS.slice(0, 4).map((k) => {
            const found = stats.by_kind.find((s) => s.kind === k)
            const occ = found?.occurrences ?? 0
            return (
              <button
                key={k}
                onClick={() => setKindFilter((prev) => (prev === k ? '' : k))}
                className={`text-left p-3 rounded-lg border transition-colors ${
                  kindFilter === k
                    ? 'bg-zinc-800 border-zinc-600'
                    : 'bg-zinc-900/40 border-zinc-800 hover:border-zinc-700'
                }`}
              >
                <p className="text-[10px] uppercase tracking-wider text-zinc-500">{KIND_LABEL[k]}</p>
                <p className={`text-2xl font-semibold mt-0.5 ${occ === 0 ? 'text-zinc-600' : 'text-zinc-100'}`}>
                  {occ}
                </p>
              </button>
            )
          })}
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            placeholder="Search message..."
            className="w-full pl-9 pr-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-600"
          />
        </div>
        <select
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value as Source | '')}
          className="px-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900 text-sm text-zinc-200 outline-none focus:border-zinc-600"
        >
          <option value="">All sources</option>
          <option value="api">API</option>
          <option value="celery">Celery</option>
          <option value="worker">Worker</option>
          <option value="startup">Startup</option>
        </select>
        <select
          value={sinceHours}
          onChange={(e) => setSinceHours(parseInt(e.target.value, 10))}
          className="px-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900 text-sm text-zinc-200 outline-none focus:border-zinc-600"
        >
          <option value={1}>Last hour</option>
          <option value={24}>Last 24 hours</option>
          <option value={168}>Last 7 days</option>
          <option value={720}>Last 30 days</option>
        </select>
        <label className="flex items-center gap-2 px-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900 text-xs text-zinc-300 cursor-pointer">
          <input
            type="checkbox"
            checked={showResolved}
            onChange={(e) => setShowResolved(e.target.checked)}
            className="accent-zinc-500"
          />
          Show resolved
        </label>
        {kindFilter && (
          <button
            onClick={() => setKindFilter('')}
            className="px-3 py-2 rounded-lg text-xs text-zinc-400 hover:text-zinc-200"
          >
            Clear kind
          </button>
        )}
      </div>

      {/* List */}
      <div className="rounded-xl border border-zinc-800 overflow-hidden">
        {loading && items.length === 0 ? (
          <p className="p-8 text-center text-sm text-zinc-500">Loading...</p>
        ) : items.length === 0 ? (
          <p className="p-8 text-center text-sm text-zinc-500">
            No errors in the selected window. 🎉
          </p>
        ) : (
          <div className="divide-y divide-zinc-800">
            {items.map((item) => {
              const isOpen = expanded.has(item.id)
              const isResolved = !!item.resolved_at
              return (
                <div key={item.id} className={isResolved ? 'opacity-60' : ''}>
                  <button
                    onClick={() => toggleExpand(item.id)}
                    className="w-full text-left px-4 py-3 hover:bg-zinc-800/30 transition-colors"
                  >
                    <div className="flex items-start gap-3">
                      <div className="shrink-0 mt-0.5 text-zinc-500">
                        {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className={`text-[10px] font-medium uppercase px-2 py-0.5 rounded-full border ${KIND_COLOR[item.kind]}`}
                          >
                            {KIND_LABEL[item.kind]}
                          </span>
                          <span className="text-[10px] font-mono text-zinc-500">{item.source}</span>
                          {item.occurrences > 1 && (
                            <span className="text-[10px] font-mono text-amber-400">
                              {item.occurrences}×
                            </span>
                          )}
                          {item.request_status != null && (
                            <span className="text-[10px] font-mono text-zinc-400">
                              {item.request_status}
                            </span>
                          )}
                          <span className="text-[10px] text-zinc-500">{relTime(item.last_seen)}</span>
                          {item.user_email && (
                            <span className="text-[10px] text-zinc-500">· {item.user_email}</span>
                          )}
                        </div>
                        <p className="text-sm text-zinc-200 mt-1 line-clamp-2 break-words">
                          {item.exception_type && (
                            <span className="font-mono text-red-300">{item.exception_type}: </span>
                          )}
                          {item.message}
                        </p>
                        {(item.request_path || item.logger_name) && (
                          <p className="text-[11px] font-mono text-zinc-500 mt-1 truncate">
                            {item.request_method ? `${item.request_method} ` : ''}
                            {item.request_path || item.logger_name}
                          </p>
                        )}
                      </div>
                    </div>
                  </button>
                  {isOpen && (
                    <div className="px-4 pb-4 pl-11 space-y-3 bg-zinc-900/30">
                      {item.traceback && (
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <p className="text-[10px] uppercase tracking-wider text-zinc-500">
                              Traceback
                            </p>
                            <button
                              onClick={() => copyText(item.traceback!, item.id)}
                              className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300"
                            >
                              {copied === item.id ? <Check size={10} /> : <Copy size={10} />}
                              {copied === item.id ? 'Copied' : 'Copy'}
                            </button>
                          </div>
                          <pre className="text-[11px] font-mono text-zinc-300 bg-zinc-950/80 p-3 rounded border border-zinc-800 overflow-x-auto whitespace-pre-wrap max-h-96 overflow-y-auto">
                            {item.traceback}
                          </pre>
                        </div>
                      )}
                      {item.context && Object.keys(item.context).length > 0 && (
                        <div>
                          <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Context</p>
                          <pre className="text-[11px] font-mono text-zinc-300 bg-zinc-950/80 p-3 rounded border border-zinc-800 overflow-x-auto max-h-40 overflow-y-auto">
                            {JSON.stringify(item.context, null, 2)}
                          </pre>
                        </div>
                      )}
                      <div className="flex items-center gap-3 text-[10px] text-zinc-500 font-mono flex-wrap">
                        <span>first: {relTime(item.first_seen)}</span>
                        <span>host: {item.hostname || '—'}</span>
                        <span>fp: {item.fingerprint.slice(0, 8)}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {isResolved ? (
                          <button
                            onClick={() => unresolve(item.id)}
                            className="px-3 py-1 rounded bg-zinc-800 text-xs text-zinc-300 hover:bg-zinc-700"
                          >
                            Mark unresolved
                          </button>
                        ) : (
                          <button
                            onClick={() => resolve(item.id)}
                            className="px-3 py-1 rounded bg-emerald-800/40 border border-emerald-700/50 text-xs text-emerald-200 hover:bg-emerald-800/60"
                          >
                            Mark resolved
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Top */}
      {stats && stats.top.length > 0 && (
        <div className="mt-6">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-2">
            Most frequent
          </h2>
          <div className="rounded-xl border border-zinc-800 overflow-hidden">
            {stats.top.slice(0, 10).map((m) => (
              <div
                key={m.id}
                className="flex items-center gap-3 px-4 py-2 border-b border-zinc-800/50 last:border-b-0"
              >
                <span className="text-xs font-mono text-amber-400 w-10 text-right">{m.occurrences}×</span>
                <span
                  className={`text-[9px] font-medium uppercase px-1.5 py-0.5 rounded border ${KIND_COLOR[m.kind]}`}
                >
                  {KIND_LABEL[m.kind]}
                </span>
                <p className="text-xs text-zinc-300 flex-1 truncate">
                  {m.exception_type && <span className="text-red-300">{m.exception_type}: </span>}
                  {m.message}
                </p>
                <span className="text-[10px] text-zinc-500">{relTime(m.last_seen)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
