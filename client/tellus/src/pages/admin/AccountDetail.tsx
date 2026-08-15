import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Button, Card, Chip, ErrorText, Input, Select, Spinner } from '../../components/ui'
import { AuditList } from './AuditList'
import type {
  AdminAccountDetail,
  AdminPasswordResetResponse,
  AdminPointsAdjustResult,
  AdminTierActionResult,
} from '../../api/types'

const LABEL = 'font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-tu-faint'
const fmtDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
const fmtDateTime = (iso: string) => new Date(iso).toLocaleString()

export default function AdminAccountDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [data, setData] = useState<AdminAccountDetail | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const [resetUrl, setResetUrl] = useState('')
  const [copyLabel, setCopyLabel] = useState('Copy')

  const [delta, setDelta] = useState('')
  const [description, setDescription] = useState('')
  const [clamp, setClamp] = useState(false)
  const [adjustError, setAdjustError] = useState('')
  const idemKeyRef = useRef<string>(crypto.randomUUID())
  const [giftDuration, setGiftDuration] = useState('30')
  const [giftNote, setGiftNote] = useState('')

  async function refresh() {
    if (!id) return
    try {
      const detail = await tellusApi.get<AdminAccountDetail>(`/admin/accounts/${id}`)
      setData(detail)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load account')
    }
  }

  useEffect(() => { void refresh() }, [id])

  async function withBusy(fn: () => Promise<void>) {
    setBusy(true)
    try { await fn() } catch (e) { setError(e instanceof Error ? e.message : 'Action failed') }
    finally { setBusy(false) }
  }

  async function suspend() {
    const reason = window.prompt('Reason (optional):')
    if (reason === null) return
    if (!window.confirm('Suspend this account? They will be signed out and unable to log in.')) return
    await withBusy(async () => {
      await tellusApi.post(`/admin/accounts/${id}/suspend`, { reason: reason || null })
      await refresh()
    })
  }

  async function unsuspend() {
    if (!window.confirm('Restore this account to active?')) return
    await withBusy(async () => {
      await tellusApi.post(`/admin/accounts/${id}/unsuspend`)
      await refresh()
    })
  }

  async function forceLogout() {
    if (!window.confirm('Sign this account out of every active session?')) return
    await withBusy(async () => {
      await tellusApi.post(`/admin/accounts/${id}/force-logout`)
    })
  }

  async function verifyEmail() {
    await withBusy(async () => {
      await tellusApi.post(`/admin/accounts/${id}/verify-email`)
      await refresh()
    })
  }

  async function generateResetLink() {
    await withBusy(async () => {
      const res = await tellusApi.post<AdminPasswordResetResponse>(`/admin/accounts/${id}/password-reset`)
      setResetUrl(res.reset_url)
      setCopyLabel('Copy')
    })
  }

  function copyResetUrl() {
    void navigator.clipboard.writeText(resetUrl)
    setCopyLabel('Copied!')
  }

  function openAdjustForm() {
    idemKeyRef.current = crypto.randomUUID()
    setDelta('')
    setDescription('')
    setClamp(false)
    setAdjustError('')
  }

  async function submitAdjust(e: React.FormEvent) {
    e.preventDefault()
    setAdjustError('')
    const n = Number(delta)
    if (!Number.isFinite(n) || n === 0) { setAdjustError('Enter a non-zero delta.'); return }
    if (n < 0 && !window.confirm(`Claw back ${-n} points from this account?`)) return
    setBusy(true)
    try {
      const result = await tellusApi.post<AdminPointsAdjustResult>(`/admin/accounts/${id}/points-adjust`, {
        delta: n, description, idempotency_key: idemKeyRef.current, clamp,
      })
      if (!result.adjusted) {
        setAdjustError('This adjustment was already applied — no change was made.')
        return
      }
      openAdjustForm()
      await refresh()
    } catch (e) {
      setAdjustError(e instanceof Error ? e.message : 'Adjustment failed')
    } finally {
      setBusy(false)
    }
  }

  async function updateTier(action: 'grant' | 'revoke') {
    if (action === 'revoke' && !window.confirm('Revoke this consumer\'s paid tier now?')) return
    await withBusy(async () => {
      const result = await tellusApi.post<AdminTierActionResult>(`/admin/accounts/${id}/tier`, {
        action,
        duration_days: action === 'grant' && giftDuration ? Number(giftDuration) : null,
        note: giftNote || null,
      })
      setGiftNote('')
      setData((current) => current ? { ...current, account: {
        ...current.account,
        consumer_tier: result.consumer_tier,
        consumer_tier_expires_at: result.consumer_tier_expires_at,
      } } : current)
      await refresh()
    })
  }

  if (error && !data) return <p className="p-4 text-sm text-tu-bad">{error}</p>
  if (!data) return <Spinner />

  const { account } = data
  const paidTierActive = account.consumer_tier === 'paid' && (
    account.consumer_tier_expires_at === null || new Date(account.consumer_tier_expires_at) > new Date()
  )
  const paidTierExpired = account.consumer_tier === 'paid' && !paidTierActive

  return (
    <div className="space-y-4 pb-8">
      <button onClick={() => navigate('/admin/accounts')} className="flex items-center gap-1 text-xs text-tu-faint hover:text-tu-text">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to accounts
      </button>

      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold text-tu-text">{account.display_name || account.email}</h1>
          <Chip tone={account.account_type === 'brand' ? 'neutral' : undefined}>{account.account_type}</Chip>
          <Chip tone={account.status === 'suspended' ? 'negative' : 'positive'}>{account.status}</Chip>
          {!account.email_verified && <Chip tone="negative">unverified</Chip>}
        </div>
        <div className="mt-1 text-sm text-tu-dim">{account.email}</div>
        {account.brand_id && (
          <button
            onClick={() => navigate(`/admin/brands/${account.brand_id}`)}
            className="mt-1 text-xs text-tu-accent hover:underline"
          >
            Owns brand: {account.brand_name}
          </button>
        )}
        <ErrorText>{error}</ErrorText>
      </Card>

      {account.account_type === 'consumer' && (
        <Card>
          <div className={`mb-2 ${LABEL}`}>Consumer tier</div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Chip tone={paidTierActive ? 'positive' : paidTierExpired ? 'negative' : undefined}>
              {paidTierActive ? 'paid' : paidTierExpired ? 'paid (expired)' : 'free'}
            </Chip>
            {paidTierActive && account.consumer_tier_expires_at && (
              <span className="text-tu-dim">through {fmtDate(account.consumer_tier_expires_at)}</span>
            )}
            {paidTierActive && !account.consumer_tier_expires_at && (
              <span className="text-tu-dim">permanent gift</span>
            )}
          </div>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <div className="w-36">
              <Select
                label="Gift duration"
                value={giftDuration}
                onChange={(e) => setGiftDuration(e.target.value)}
                options={[
                  { value: '30', label: '30 days' },
                  { value: '90', label: '90 days' },
                  { value: '365', label: '1 year' },
                  { value: '', label: 'Permanent' },
                ]}
              />
            </div>
            <div className="min-w-[14rem] flex-1">
              <Input label="Gift note" value={giftNote} onChange={(e) => setGiftNote(e.target.value)} placeholder="Why is this being gifted?" />
            </div>
            <Button size="sm" loading={busy} onClick={() => void updateTier('grant')}>Gift paid tier</Button>
            {paidTierActive && (
              <Button size="sm" variant="danger" loading={busy} onClick={() => void updateTier('revoke')}>Revoke</Button>
            )}
          </div>
        </Card>
      )}

      <Card>
        <div className={`mb-3 ${LABEL}`}>Actions</div>
        <div className="flex flex-wrap gap-2">
          {account.status === 'active'
            ? <Button variant="danger" size="sm" loading={busy} onClick={() => void suspend()}>Suspend</Button>
            : <Button variant="soft" size="sm" loading={busy} onClick={() => void unsuspend()}>Unsuspend</Button>}
          <Button variant="soft" size="sm" loading={busy} onClick={() => void forceLogout()}>Force sign-out</Button>
          {!account.email_verified && (
            <Button variant="soft" size="sm" loading={busy} onClick={() => void verifyEmail()}>Verify email</Button>
          )}
          <Button variant="soft" size="sm" loading={busy} onClick={() => void generateResetLink()}>Generate reset link</Button>
        </div>

        {resetUrl && (
          <div className="mt-3 flex items-end gap-2">
            <div className="flex-1"><Input label="Password reset link (expires in 1 hour)" readOnly value={resetUrl} /></div>
            <Button variant="soft" size="sm" onClick={copyResetUrl}>{copyLabel}</Button>
          </div>
        )}

        <div className="mt-4 border-t border-tu-border/70 pt-4">
          <div className={`mb-2 ${LABEL}`}>Adjust points</div>
          <form onSubmit={submitAdjust} className="flex flex-wrap items-end gap-2">
            <div className="w-28"><Input label="Delta" type="number" value={delta} onChange={(e) => setDelta(e.target.value)} placeholder="+50 / -50" /></div>
            <div className="flex-1 min-w-[12rem]"><Input label="Reason" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Why is this adjustment being made?" /></div>
            {Number(delta) < 0 && (
              <label className="flex items-center gap-1.5 pb-2 text-xs text-tu-dim">
                <input type="checkbox" checked={clamp} onChange={(e) => setClamp(e.target.checked)} />
                Clamp to balance
              </label>
            )}
            <Button type="submit" size="sm" loading={busy}>Apply</Button>
          </form>
          <ErrorText>{adjustError}</ErrorText>
        </div>
      </Card>

      <Card>
        <div className={`mb-2 ${LABEL}`}>Points</div>
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <span>Balance <b className="tabular-nums text-tu-text">{account.points_balance}</b></span>
          <span>Lifetime <b className="tabular-nums text-tu-text">{data.lifetime_points}</b></span>
          <span>Level <b className="text-tu-text">{data.level}</b></span>
          <span>Streak <b className="text-tu-text">{data.current_streak}</b></span>
        </div>
      </Card>

      <Card>
        <div className={`mb-2 ${LABEL}`}>Ledger</div>
        {data.ledger.length === 0 && <p className="text-sm text-tu-faint">No ledger entries yet.</p>}
        <div className="space-y-1">
          {data.ledger.map((l) => (
            <div key={l.id} className="flex items-center justify-between border-b border-tu-border/50 py-1.5 text-sm last:border-b-0">
              <div className="flex items-center gap-2">
                <span className={l.delta >= 0 ? 'font-mono text-tu-good' : 'font-mono text-tu-bad'}>
                  {l.delta >= 0 ? `+${l.delta}` : l.delta}
                </span>
                <Chip>{l.reason}</Chip>
                <span className="text-tu-dim">{l.description}</span>
              </div>
              <span className="shrink-0 text-xs text-tu-faint">{fmtDateTime(l.created_at)}</span>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <div className={`mb-2 ${LABEL}`}>Reviews</div>
          {data.recent_reports.length === 0 && <p className="text-sm text-tu-faint">None yet.</p>}
          {data.recent_reports.map((r) => (
            <div key={r.id} className="border-b border-tu-border/50 py-1.5 text-sm last:border-b-0">
              <div className="flex items-center gap-2">
                <span className="text-tu-text">{r.title || '(no title)'}</span>
                <Chip>{r.moderation_status}</Chip>
                {r.review_state && <Chip tone={r.review_state === 'published' ? 'positive' : undefined}>{r.review_state}</Chip>}
              </div>
              <div className="text-xs text-tu-faint">{r.brand_name} · {fmtDate(r.created_at)}</div>
            </div>
          ))}
        </Card>
        <Card>
          <div className={`mb-2 ${LABEL}`}>Redemptions</div>
          {data.redemptions.length === 0 && <p className="text-sm text-tu-faint">None yet.</p>}
          {data.redemptions.map((r) => (
            <div key={r.id} className="flex items-center justify-between border-b border-tu-border/50 py-1.5 text-sm last:border-b-0">
              <span className="text-tu-text">{r.listing_title}</span>
              <Chip>{r.status}</Chip>
            </div>
          ))}
        </Card>
      </div>

      <Card>
        <div className={`mb-2 ${LABEL}`}>DM threads</div>
        {data.dm_threads.length === 0 && <p className="text-sm text-tu-faint">None yet.</p>}
        {data.dm_threads.map((t) => (
          <div key={t.id} className="flex items-center justify-between border-b border-tu-border/50 py-1.5 text-sm last:border-b-0">
            <span className="text-tu-text">{t.brand_name}</span>
            {t.blocked && <Chip tone="negative">blocked</Chip>}
          </div>
        ))}
      </Card>

      <Card>
        <div className={`mb-2 ${LABEL}`}>Audit history</div>
        <AuditList entries={data.audit} emptyText="No admin actions on this account yet." />
      </Card>

      {busy && <div className="fixed bottom-4 right-4"><Loader2 className="h-5 w-5 animate-spin text-tu-accent" /></div>}
    </div>
  )
}
