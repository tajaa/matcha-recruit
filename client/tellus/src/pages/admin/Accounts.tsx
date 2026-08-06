import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Sparkles } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Chip, Input, Select } from '../../components/ui'
import type { AdminAccountList, AdminAccountSummary } from '../../api/types'

const fmtDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })

export default function AdminAccounts() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [accountType, setAccountType] = useState('')
  const [status, setStatus] = useState('')
  const [verified, setVerified] = useState('')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<AdminAccountList | null>(null)
  const [loading, setLoading] = useState(false)
  const limit = 50

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 300)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => { setOffset(0) }, [debouncedQ, accountType, status, verified])

  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (debouncedQ) params.set('q', debouncedQ)
    if (accountType) params.set('account_type', accountType)
    if (status) params.set('status', status)
    if (verified) params.set('verified', verified)
    params.set('limit', String(limit))
    params.set('offset', String(offset))
    tellusApi.get<AdminAccountList>(`/admin/accounts?${params.toString()}`)
      .then(setData)
      .finally(() => setLoading(false))
  }, [debouncedQ, accountType, status, verified, offset])

  const statusTone = (s: string) => (s === 'suspended' ? 'negative' : 'positive')

  const items = useMemo(() => data?.items ?? [], [data])

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col overflow-hidden rounded-xl border border-tu-border bg-tu-bg">
      <div className="flex items-center justify-between border-b border-tu-border px-4 py-3">
        <h1 className="flex items-center gap-2 text-sm font-semibold text-tu-text">
          <Sparkles className="h-4 w-4 text-tu-accent" /> Accounts
        </h1>
        <span className="text-xs text-tu-faint">{data?.total ?? '—'} total</span>
      </div>

      <div className="flex flex-wrap items-end gap-3 border-b border-tu-border px-4 py-3">
        <div className="w-56">
          <Input placeholder="Search email or name…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="w-36">
          <Select
            value={accountType}
            onChange={(e) => setAccountType(e.target.value)}
            options={[{ value: '', label: 'All types' }, { value: 'consumer', label: 'Consumer' }, { value: 'brand', label: 'Brand' }]}
          />
        </div>
        <div className="w-36">
          <Select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            options={[{ value: '', label: 'All statuses' }, { value: 'active', label: 'Active' }, { value: 'suspended', label: 'Suspended' }]}
          />
        </div>
        <div className="w-40">
          <Select
            value={verified}
            onChange={(e) => setVerified(e.target.value)}
            options={[{ value: '', label: 'Any verification' }, { value: 'true', label: 'Verified' }, { value: 'false', label: 'Unverified' }]}
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && !data && <Loader2 className="m-4 h-5 w-5 animate-spin text-tu-faint" />}
        {items.map((a: AdminAccountSummary) => (
          <button
            key={a.id}
            type="button"
            onClick={() => navigate(`/admin/accounts/${a.id}`)}
            className="flex w-full items-center justify-between gap-3 border-b border-tu-border/70 px-4 py-3 text-left transition-colors hover:bg-tu-panel2/60"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium text-tu-text">{a.display_name || a.email}</span>
                <Chip tone={a.account_type === 'brand' ? 'neutral' : undefined}>{a.account_type}</Chip>
                <Chip tone={statusTone(a.status)}>{a.status}</Chip>
                {!a.email_verified && <Chip tone="negative">unverified</Chip>}
              </div>
              <div className="mt-0.5 truncate text-xs text-tu-faint">{a.email}</div>
            </div>
            <div className="shrink-0 text-right text-xs text-tu-faint">
              <div className="tabular-nums text-tu-text">{a.points_balance} pts</div>
              <div>{fmtDate(a.created_at)}</div>
            </div>
          </button>
        ))}
        {!loading && items.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-tu-faint">No accounts match these filters.</p>
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
