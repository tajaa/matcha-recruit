import { useEffect, useState } from 'react'
import { Loader2, Sparkles } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Card, ErrorText, Input, Select } from '../../components/ui'
import { AuditList } from './AuditList'
import type { AdminAuditList } from '../../api/types'

const TARGET_TYPES = ['account', 'brand', 'report', 'dm_thread', 'earning_rule', 'badge', 'listing']

export default function AdminAudit() {
  const [actions, setActions] = useState<string[]>([])
  const [action, setAction] = useState('')
  const [targetType, setTargetType] = useState('')
  const [targetId, setTargetId] = useState('')
  const [debouncedTargetId, setDebouncedTargetId] = useState('')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<AdminAuditList | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const limit = 50

  useEffect(() => {
    tellusApi.get<string[]>('/admin/audit/actions').then(setActions).catch(() => {})
  }, [])

  useEffect(() => {
    const t = setTimeout(() => setDebouncedTargetId(targetId), 300)
    return () => clearTimeout(t)
  }, [targetId])

  useEffect(() => { setOffset(0) }, [action, targetType, debouncedTargetId])

  useEffect(() => {
    setLoading(true)
    setError('')
    const params = new URLSearchParams()
    if (action) params.set('action', action)
    if (targetType) params.set('target_type', targetType)
    if (debouncedTargetId) params.set('target_id', debouncedTargetId)
    params.set('limit', String(limit))
    params.set('offset', String(offset))
    tellusApi.get<AdminAuditList>(`/admin/audit?${params.toString()}`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load audit log'))
      .finally(() => setLoading(false))
  }, [action, targetType, debouncedTargetId, offset])

  const items = data?.items ?? []

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col overflow-hidden rounded-xl border border-tu-border bg-tu-bg">
      <div className="flex items-center justify-between border-b border-tu-border px-4 py-3">
        <h1 className="flex items-center gap-2 text-sm font-semibold text-tu-text">
          <Sparkles className="h-4 w-4 text-tu-accent" /> Audit
        </h1>
        <span className="text-xs text-tu-faint">{data?.total ?? '—'} total</span>
      </div>

      <div className="flex flex-wrap items-end gap-3 border-b border-tu-border px-4 py-3">
        <div className="w-56">
          <Select
            value={action}
            onChange={(e) => setAction(e.target.value)}
            options={[{ value: '', label: 'All actions' }, ...actions.map((a) => ({ value: a, label: a }))]}
          />
        </div>
        <div className="w-40">
          <Select
            value={targetType}
            onChange={(e) => setTargetType(e.target.value)}
            options={[{ value: '', label: 'All target types' }, ...TARGET_TYPES.map((t) => ({ value: t, label: t }))]}
          />
        </div>
        <div className="w-56">
          <Input placeholder="Target id…" value={targetId} onChange={(e) => setTargetId(e.target.value)} />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4">
        {error && <ErrorText>{error}</ErrorText>}
        {loading && items.length === 0 && <Loader2 className="m-4 h-5 w-5 animate-spin text-tu-faint" />}
        {!loading && items.length === 0 && !error && (
          <p className="px-1 py-8 text-center text-sm text-tu-faint">No admin actions match these filters.</p>
        )}
        {items.length > 0 && (
          <Card>
            <AuditList entries={items} showTarget />
          </Card>
        )}
      </div>

      <div className="flex items-center justify-between border-t border-tu-border px-4 py-2">
        <button
          type="button"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - limit))}
          className="rounded-md border border-tu-border px-2.5 py-1 text-xs font-medium text-tu-dim disabled:opacity-40"
        >
          Prev
        </button>
        <span className="text-xs text-tu-faint">
          {data ? `${offset + 1}–${Math.min(offset + limit, data.total)} of ${data.total}` : ''}
        </span>
        <button
          type="button"
          disabled={!data || offset + limit >= data.total}
          onClick={() => setOffset(offset + limit)}
          className="rounded-md border border-tu-border px-2.5 py-1 text-xs font-medium text-tu-dim disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  )
}
