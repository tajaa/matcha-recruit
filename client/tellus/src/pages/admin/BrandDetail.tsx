import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Button, Card, Chip, ErrorText, Input, Spinner } from '../../components/ui'
import type { AdminAccountList, AdminAccountSummary, AdminBrandDetail, AdminPlanActionResult } from '../../api/types'

const LABEL = 'font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-tu-faint'
const PLAN_TONE: Record<string, string> = {
  active: 'positive', past_due: 'negative', canceled: 'negative', pending: 'neutral',
}
const fmtDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
const fmtDateTime = (iso: string) => new Date(iso).toLocaleString()

export default function AdminBrandDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [data, setData] = useState<AdminBrandDetail | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [stripeWarning, setStripeWarning] = useState('')

  const [ownerQuery, setOwnerQuery] = useState('')
  const [ownerResults, setOwnerResults] = useState<AdminAccountSummary[]>([])
  const [searching, setSearching] = useState(false)

  async function refresh() {
    if (!id) return
    try {
      const detail = await tellusApi.get<AdminBrandDetail>(`/admin/brands/${id}`)
      setData(detail)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load brand')
    }
  }

  useEffect(() => { void refresh() }, [id])

  useEffect(() => {
    if (!ownerQuery || data?.brand.owner_account_id) { setOwnerResults([]); return }
    const t = setTimeout(async () => {
      setSearching(true)
      try {
        const res = await tellusApi.get<AdminAccountList>(`/admin/accounts?q=${encodeURIComponent(ownerQuery)}&limit=10`)
        setOwnerResults(res.items.filter((a) => !a.brand_id))
      } finally {
        setSearching(false)
      }
    }, 300)
    return () => clearTimeout(t)
  }, [ownerQuery, data?.brand.owner_account_id])

  async function comp() {
    if (!window.confirm('Grant this brand an active plan without payment?')) return
    setBusy(true)
    try {
      const res = await tellusApi.post<AdminPlanActionResult>(`/admin/brands/${id}/plan`, { action: 'comp' })
      setStripeWarning(res.stripe_warning || '')
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to comp plan')
    } finally {
      setBusy(false)
    }
  }

  async function cancel() {
    if (!window.confirm('Cancel this brand\'s plan?')) return
    setBusy(true)
    try {
      const res = await tellusApi.post<AdminPlanActionResult>(`/admin/brands/${id}/plan`, { action: 'cancel' })
      setStripeWarning(res.stripe_warning || '')
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to cancel plan')
    } finally {
      setBusy(false)
    }
  }

  async function assignOwner(account: AdminAccountSummary) {
    const note = account.account_type === 'consumer'
      ? 'This will convert the consumer account to a brand account and hand it this brand. Continue?'
      : 'Assign this account as the owner of this brand?'
    if (!window.confirm(note)) return
    setBusy(true)
    try {
      await tellusApi.post(`/admin/brands/${id}/assign-owner`, { account_id: account.id })
      setOwnerQuery('')
      setOwnerResults([])
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to assign owner')
    } finally {
      setBusy(false)
    }
  }

  if (error && !data) return <p className="p-4 text-sm text-tu-bad">{error}</p>
  if (!data) return <Spinner />

  const { brand } = data

  return (
    <div className="space-y-4 pb-8">
      <button onClick={() => navigate('/admin/brands')} className="flex items-center gap-1 text-xs text-tu-faint hover:text-tu-text">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to brands
      </button>

      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold text-tu-text">{brand.name}</h1>
          <Chip tone={PLAN_TONE[brand.plan_status]}>{brand.plan_status}</Chip>
          <Chip>{brand.source}</Chip>
        </div>
        <div className="mt-1 font-mono text-sm text-tu-dim">{brand.slug}</div>
        <div className="mt-2 text-sm">
          {brand.owner_account_id
            ? <button onClick={() => navigate(`/admin/accounts/${brand.owner_account_id}`)} className="text-tu-accent hover:underline">Owner: {brand.owner_email}</button>
            : <span className="italic text-tu-faint">unclaimed</span>}
        </div>
        {data.activated_at && <div className="mt-1 text-xs text-tu-faint">Activated {fmtDate(data.activated_at)}</div>}
        {data.claimed_at && <div className="text-xs text-tu-faint">Claimed {fmtDate(data.claimed_at)}</div>}
        {(data.stripe_customer_id || data.stripe_subscription_id) && (
          <div className="mt-1 space-y-0.5 font-mono text-xs text-tu-faint">
            {data.stripe_customer_id && <div>customer: {data.stripe_customer_id}</div>}
            {data.stripe_subscription_id && <div>subscription: {data.stripe_subscription_id}</div>}
          </div>
        )}
        <ErrorText>{error}</ErrorText>
      </Card>

      <Card>
        <div className={`mb-3 ${LABEL}`}>Plan</div>
        <div className="flex flex-wrap gap-2">
          {brand.plan_status !== 'active' && <Button variant="soft" size="sm" loading={busy} onClick={() => void comp()}>Comp (grant active)</Button>}
          {(brand.plan_status === 'active' || brand.plan_status === 'past_due') && (
            <Button variant="danger" size="sm" loading={busy} onClick={() => void cancel()}>Cancel plan</Button>
          )}
        </div>
        {stripeWarning && (
          <p className="mt-2 text-sm text-tu-accent">{stripeWarning}</p>
        )}
      </Card>

      {!brand.owner_account_id && (
        <Card>
          <div className={`mb-2 ${LABEL}`}>Assign owner</div>
          <Input placeholder="Search accounts by email or name…" value={ownerQuery} onChange={(e) => setOwnerQuery(e.target.value)} />
          {searching && <Loader2 className="mt-2 h-4 w-4 animate-spin text-tu-faint" />}
          <div className="mt-2 space-y-1">
            {ownerResults.map((a) => (
              <div key={a.id} className="flex items-center justify-between rounded-md border border-tu-border/70 px-3 py-2 text-sm">
                <span className="text-tu-text">{a.display_name || a.email} <span className="text-tu-faint">({a.email})</span></span>
                <Button size="sm" variant="soft" loading={busy} onClick={() => void assignOwner(a)}>Assign</Button>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <div className={`mb-2 ${LABEL}`}>Stores</div>
          {data.stores.length === 0 && <p className="text-sm text-tu-faint">None yet. (billed: {brand.location_count})</p>}
          {data.stores.map((s) => (
            <div key={s.id} className="border-b border-tu-border/50 py-1 text-sm last:border-b-0">
              <div className="text-tu-text">{s.name}</div>
              <div className="text-xs text-tu-faint">{[s.city, s.state].filter(Boolean).join(', ')}</div>
            </div>
          ))}
        </Card>
        <Card>
          <div className={`mb-2 ${LABEL}`}>Links</div>
          {data.links.length === 0 && <p className="text-sm text-tu-faint">None yet.</p>}
          {data.links.map((l) => (
            <div key={l.id} className="flex items-center justify-between border-b border-tu-border/50 py-1 text-sm last:border-b-0">
              <span className="font-mono text-xs text-tu-faint">{l.id.slice(0, 8)}</span>
              <Chip tone={l.is_active ? 'positive' : 'negative'}>{l.is_active ? 'active' : 'revoked'}</Chip>
            </div>
          ))}
        </Card>
        <Card>
          <div className={`mb-2 ${LABEL}`}>Prompts</div>
          {data.prompts.length === 0 && <p className="text-sm text-tu-faint">None yet.</p>}
          {data.prompts.map((p) => (
            <div key={p.id} className="border-b border-tu-border/50 py-1 text-sm text-tu-text last:border-b-0">{p.prompt}</div>
          ))}
        </Card>
      </div>

      <Card>
        <div className={`mb-2 ${LABEL}`}>Report stats</div>
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <span>Total <b className="text-tu-text">{data.report_stats.total ?? '—'}</b></span>
          <span>Last 30 days <b className="text-tu-text">{data.report_stats.last_30d ?? '—'}</b></span>
          <span>Avg rating <b className="text-tu-text">{data.report_stats.avg_rating ?? '—'}</b></span>
        </div>
      </Card>

      <Card>
        <div className={`mb-2 ${LABEL}`}>Audit history</div>
        {data.audit.length === 0 && <p className="text-sm text-tu-faint">No admin actions on this brand yet.</p>}
        {data.audit.map((a) => (
          <details key={a.id} className="border-b border-tu-border/50 py-1.5 text-sm last:border-b-0">
            <summary className="cursor-pointer">
              <span className="text-tu-text">{a.action}</span>{' '}
              <span className="text-tu-faint">by {a.actor_email} · {fmtDateTime(a.created_at)}</span>
            </summary>
            {a.detail && <pre className="mt-1 overflow-x-auto text-xs text-tu-dim">{JSON.stringify(a.detail, null, 2)}</pre>}
          </details>
        ))}
      </Card>
    </div>
  )
}
