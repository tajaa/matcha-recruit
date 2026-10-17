/* eslint-disable react-hooks/set-state-in-effect -- Effects intentionally synchronize this tool with loaded data, URL selections, and preview inputs. */
import { AdminButton, AdminInput } from '../../../components/admin/AdminUI'
import { useEffect, useState, useCallback } from 'react'
import { Copy } from 'lucide-react'
import { api } from '../../../api/client'
import { ErrorConsole, ErrorTimeFilter } from '../../../components/admin/ErrorConsole'

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

export default function ClientErrors() {
  const [items, setItems] = useState<ErrorItem[]>([])
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [kindFilter, setKindFilter] = useState<Kind | ''>('')
  const [emailFilter, setEmailFilter] = useState('')
  const [sinceHours, setSinceHours] = useState(24)
  const [total, setTotal] = useState(0)

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

  async function copyStack(stack: string) {
    try {
      await navigator.clipboard.writeText(stack)
    } catch { /* Preserve the existing best-effort fallback. */ }
  }

  return (
    <ErrorConsole
      title="Browser errors"
      description={<>React, API, and uncaught browser errors — last {sinceHours} hours ({total} total).</>}
      loading={loading}
      onRefresh={refresh}
      kinds={(Object.keys(KIND_LABEL) as Kind[]).map((key) => ({ key, label: KIND_LABEL[key], color: KIND_COLOR[key], count: stats?.by_kind.find((row) => row.kind === key)?.count ?? 0 }))}
      selectedKind={kindFilter}
      onKindChange={(value) => setKindFilter(value as Kind | '')}
      filters={<><AdminInput aria-label="Filter by user email" value={emailFilter} onChange={(event) => setEmailFilter(event.target.value)} placeholder="Filter by user email…" className="max-w-xs" /><ErrorTimeFilter value={sinceHours} onChange={setSinceHours} /></>}
      items={items}
      summary={(item) => ({ id: item.id, kind: item.kind, title: item.message, subtitle: item.api_endpoint || item.url, status: item.api_status_code, at: item.occurred_at, email: item.user_email })}
      details={(item) => ({
        trace: item.stack ? { label: 'Stack trace', value: item.stack } : undefined,
        actions: item.stack ? <AdminButton variant="ghost" onClick={() => copyStack(item.stack!)}><Copy size={12} /> Copy stack</AdminButton> : null,
        context: item.context,
        fields: [{ label: 'URL', value: item.url }, { label: 'User agent', value: item.user_agent }, { label: 'Error ID', value: item.id }].filter((field) => !!field.value),
      })}
      top={(stats?.top_messages ?? []).map((item, index) => ({ id: String(index), kind: item.kind, count: item.count, title: item.message, at: item.last_seen }))}
    />
  )
}
