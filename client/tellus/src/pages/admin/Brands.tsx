import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Sparkles } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Chip, Input, Select } from '../../components/ui'
import type { AdminBrandList, AdminBrandSummary } from '../../api/types'

const PLAN_TONE: Record<string, string> = {
  active: 'positive', past_due: 'negative', canceled: 'negative', pending: 'neutral',
}

export default function AdminBrands() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [planStatus, setPlanStatus] = useState('')
  const [source, setSource] = useState('')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<AdminBrandList | null>(null)
  const [loading, setLoading] = useState(false)
  const limit = 50

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 300)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => { setOffset(0) }, [debouncedQ, planStatus, source])

  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (debouncedQ) params.set('q', debouncedQ)
    if (planStatus) params.set('plan_status', planStatus)
    if (source) params.set('source', source)
    params.set('limit', String(limit))
    params.set('offset', String(offset))
    tellusApi.get<AdminBrandList>(`/admin/brands?${params.toString()}`)
      .then(setData)
      .finally(() => setLoading(false))
  }, [debouncedQ, planStatus, source, offset])

  const items = useMemo(() => data?.items ?? [], [data])

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col overflow-hidden rounded-xl border border-tu-border bg-tu-bg">
      <div className="flex items-center justify-between border-b border-tu-border px-4 py-3">
        <h1 className="flex items-center gap-2 text-sm font-semibold text-tu-text">
          <Sparkles className="h-4 w-4 text-tu-accent" /> Brands
        </h1>
        <span className="text-xs text-tu-faint">{data?.total ?? '—'} total</span>
      </div>

      <div className="flex flex-wrap items-end gap-3 border-b border-tu-border px-4 py-3">
        <div className="w-56">
          <Input placeholder="Search name or slug…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="w-40">
          <Select
            value={planStatus}
            onChange={(e) => setPlanStatus(e.target.value)}
            options={[
              { value: '', label: 'All plans' }, { value: 'pending', label: 'Pending' },
              { value: 'active', label: 'Active' }, { value: 'past_due', label: 'Past due' },
              { value: 'canceled', label: 'Canceled' },
            ]}
          />
        </div>
        <div className="w-40">
          <Select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            options={[{ value: '', label: 'All sources' }, { value: 'signup', label: 'Signup' }, { value: 'consumer_added', label: 'Consumer-added' }]}
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && !data && <Loader2 className="m-4 h-5 w-5 animate-spin text-tu-faint" />}
        {items.map((b: AdminBrandSummary) => (
          <button
            key={b.id}
            type="button"
            onClick={() => navigate(`/admin/brands/${b.id}`)}
            className="flex w-full items-center justify-between gap-3 border-b border-tu-border/70 px-4 py-3 text-left transition-colors hover:bg-tu-panel2/60"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium text-tu-text">{b.name}</span>
                <Chip tone={PLAN_TONE[b.plan_status]}>{b.plan_status}</Chip>
                <Chip>{b.source}</Chip>
              </div>
              <div className="mt-0.5 truncate font-mono text-xs text-tu-faint">{b.slug}</div>
            </div>
            <div className="shrink-0 text-right text-xs">
              <div className={b.store_count !== b.location_count ? 'text-tu-bad' : 'text-tu-faint'}>
                stores {b.store_count} / billed {b.location_count}
              </div>
              <div className="text-tu-faint">{b.owner_email || <span className="italic">unclaimed</span>}</div>
            </div>
          </button>
        ))}
        {!loading && items.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-tu-faint">No brands match these filters.</p>
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
