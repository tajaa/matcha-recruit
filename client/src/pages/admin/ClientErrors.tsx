import { useEffect, useState, useCallback } from 'react'
import { AlertOctagon, RefreshCw, Search, ChevronDown, ChevronRight, Copy } from 'lucide-react'
import { api } from '../../api/client'

type Kind = 'js_error' | 'promise_rejection' | 'api_error' | 'react_error'

interface ErrorItem {
  id: string
  user_id: string | null
  user_email: string | null
  kind: Kind
  message: string
  stack: string | null
  url: string | null
  user_agent: string | null
  api_endpoint: string | null
  api_status_code: number | null
  context: Record<string, unknown> | null
  occurred_at: string | null
}

interface ListResponse {
  total: number
  items: ErrorItem[]
}

interface KindCount {
  kind: Kind
  count: number
}

interface StatsResponse {
  by_kind: KindCount[]
  top_messages: {
    message: string
    kind: Kind
    count: number
    last_seen: string | null
  }[]
}

const KIND_LABEL: Record<Kind, string> = {
  js_error: 'JS Error',
  promise_rejection: 'Promise',
  api_error: 'API',
  react_error: 'React',
}

const KIND_COLOR: Record<Kind, string> = {
  js_error: 'bg-red-500/15 text-red-300 border-red-500/30',
  promise_rejection: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
  api_error: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  react_error: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
}

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

export default function ClientErrors() {
  const [items, setItems] = useState<ErrorItem[]>([])
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [kindFilter, setKindFilter] = useState<Kind | ''>('')
  const [emailFilter, setEmailFilter] = useState('')
  const [sinceHours, setSinceHours] = useState(24)
  const [total, setTotal] = useState(0)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (kindFilter) params.set('kind', kindFilter)
      if (emailFilter) params.set('user_email', emailFilter)
      params.set('since_hours', String(sinceHours))
      params.set('limit', '100')

      const [listRes, statsRes] = await Promise.all([
        api.get<ListResponse>(`/admin/client-errors?${params.toString()}`),
        api.get<StatsResponse>(`/admin/client-errors/stats?since_hours=${sinceHours}`),
      ])
      setItems(listRes.items)
      setTotal(listRes.total)
      setStats(statsRes)
    } catch (err) {
      console.error('Failed to load client errors', err)
    } finally {
      setLoading(false)
    }
  }, [kindFilter, emailFilter, sinceHours])

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

  async function copyStack(stack: string) {
    try {
      await navigator.clipboard.writeText(stack)
    } catch {}
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="flex items-center gap-2">
            <AlertOctagon size={20} className="text-amber-500" />
            <h1 className="text-xl font-semibold text-zinc-100">Client Errors</h1>
          </div>
          <p className="text-sm text-zinc-500 mt-0.5">
            Browser errors captured from React, API calls, and uncaught JS — last {sinceHours} hours ({total} total)
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
          {(['js_error', 'promise_rejection', 'api_error', 'react_error'] as Kind[]).map((k) => {
            const found = stats.by_kind.find((s) => s.kind === k)
            const count = found?.count ?? 0
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
                <p className={`text-2xl font-semibold mt-0.5 ${count === 0 ? 'text-zinc-600' : 'text-zinc-100'}`}>
                  {count}
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
            value={emailFilter}
            onChange={(e) => setEmailFilter(e.target.value)}
            placeholder="Filter by user email..."
            className="w-full pl-9 pr-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-600"
          />
        </div>
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
        {kindFilter && (
          <button
            onClick={() => setKindFilter('')}
            className="px-3 py-2 rounded-lg text-xs text-zinc-400 hover:text-zinc-200"
          >
            Clear kind filter
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
              return (
                <div key={item.id}>
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
                          {item.api_status_code != null && (
                            <span className="text-[10px] font-mono text-zinc-400">
                              {item.api_status_code}
                            </span>
                          )}
                          <span className="text-[10px] text-zinc-500">{relTime(item.occurred_at)}</span>
                          {item.user_email && (
                            <span className="text-[10px] text-zinc-500">· {item.user_email}</span>
                          )}
                        </div>
                        <p className="text-sm text-zinc-200 mt-1 line-clamp-2 break-words">
                          {item.message}
                        </p>
                        {(item.api_endpoint || item.url) && (
                          <p className="text-[11px] font-mono text-zinc-500 mt-1 truncate">
                            {item.api_endpoint || item.url}
                          </p>
                        )}
                      </div>
                    </div>
                  </button>
                  {isOpen && (
                    <div className="px-4 pb-4 pl-11 space-y-3 bg-zinc-900/30">
                      {item.stack && (
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <p className="text-[10px] uppercase tracking-wider text-zinc-500">
                              Stack trace
                            </p>
                            <button
                              onClick={() => copyStack(item.stack!)}
                              className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300"
                            >
                              <Copy size={10} /> Copy
                            </button>
                          </div>
                          <pre className="text-[11px] font-mono text-zinc-300 bg-zinc-950/80 p-3 rounded border border-zinc-800 overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto">
                            {item.stack}
                          </pre>
                        </div>
                      )}
                      {item.url && (
                        <div>
                          <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">URL</p>
                          <p className="text-[11px] font-mono text-zinc-300 break-all">{item.url}</p>
                        </div>
                      )}
                      {item.user_agent && (
                        <div>
                          <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">
                            User agent
                          </p>
                          <p className="text-[11px] font-mono text-zinc-400 break-all">{item.user_agent}</p>
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
                      <div className="text-[10px] text-zinc-600 font-mono">id: {item.id}</div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Top messages */}
      {stats && stats.top_messages.length > 0 && (
        <div className="mt-6">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-2">
            Top errors in window
          </h2>
          <div className="rounded-xl border border-zinc-800 overflow-hidden">
            {stats.top_messages.slice(0, 10).map((m, i) => (
              <div
                key={i}
                className="flex items-center gap-3 px-4 py-2 border-b border-zinc-800/50 last:border-b-0"
              >
                <span className="text-xs font-mono text-zinc-400 w-8 text-right">{m.count}×</span>
                <span
                  className={`text-[9px] font-medium uppercase px-1.5 py-0.5 rounded border ${KIND_COLOR[m.kind]}`}
                >
                  {KIND_LABEL[m.kind]}
                </span>
                <p className="text-xs text-zinc-300 flex-1 truncate">{m.message}</p>
                <span className="text-[10px] text-zinc-500">{relTime(m.last_seen)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
