import { AdminCard, AdminInput, AdminButton, AdminSelect, AdminTable } from '../../../../components/admin/AdminUI'
import { AdminPageHeader } from '../../../../components/admin/AdminPageHeader'
import { AdminList, AdminMetricRow, AdminPagination } from '../../../../components/admin/AdminList'
import { AdminActionMenu } from '../../../../components/admin/AdminActionMenu'
import { useAdminPagination } from '../../../../components/admin/useAdminPagination'

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, Search, Zap, UserPlus, Copy, Check } from 'lucide-react'
import { api } from '../../../../api/client'
import { useAsync } from '../../../../hooks/useAsync'

interface IndividualUser {
  user_id: string
  email: string
  name: string | null
  company_id: string
  created_at: string | null
  free_tokens_used: number
  free_token_limit: number
  free_tokens_remaining: number
  subscription_token_limit: number
  subscription_tokens_remaining: number
  has_active_subscription: boolean
  beta_features?: Record<string, boolean | number>
  is_suspended?: boolean
  subscription?: {
    pack_id: string
    status: string
    amount_cents: number
    stripe_subscription_id: string
    stripe_customer_id: string
    current_period_end: string | null
    canceled_at: string | null
  } | null
}

// An admin's top-up to a person's monthly allowance of background work (job
// searches cost 5 units each); mirrors allowance.BONUS_KEY / MAX_BONUS_UNITS.
const BONUS_KEY = 'matcha_work_bonus_units'
const MAX_BONUS_UNITS = 2000
const BONUS_PRESETS = [25, 50, 100]

function bonusUnits(user: IndividualUser): number {
  const value = user.beta_features?.[BONUS_KEY]
  return typeof value === 'number' && value > 0 ? value : 0
}

function fmtUsd(cents: number) {
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`
  return String(n)
}

function relTime(iso: string | null): string {
  if (!iso) return '--'
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (d === 0) return 'Today'
  if (d === 1) return 'Yesterday'
  return `${d}d ago`
}

export default function Individuals({ embedded = false }: { embedded?: boolean }) {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [plan, setPlan] = useState('all')
  const [sort, setSort] = useState('newest')
  const [grantTarget, setGrantTarget] = useState<IndividualUser | null>(null)
  const [grantAmount, setGrantAmount] = useState('')
  const [granting, setGranting] = useState(false)
  const [bonusTarget, setBonusTarget] = useState<IndividualUser | null>(null)
  const [bonusAmount, setBonusAmount] = useState('')
  const [savingBonus, setSavingBonus] = useState(false)
  const [showInvite, setShowInvite] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteResult, setInviteResult] = useState<{ invite_url: string; email: string; reused: boolean } | null>(null)
  const [inviteError, setInviteError] = useState('')
  const [inviting, setInviting] = useState(false)
  const [copied, setCopied] = useState(false)

  const {
    data: users,
    loading,
    error,
    setData: setUsers,
    reload: fetchUsers,
  } = useAsync(() => api.get<IndividualUser[]>('/matcha-work/billing/admin/individuals'), [], [])

  async function toggleBetaFlag(userId: string, flag: string, value: boolean) {
    setUsers(prev => prev.map(u =>
      u.user_id === userId
        ? { ...u, beta_features: { ...u.beta_features, [flag]: value } }
        : u
    ))
    try {
      await api.patch(`/admin/users/${userId}/beta-flags`, { [flag]: value })
    } finally {
      fetchUsers()
    }
  }

  async function handleCreateInvite() {
    if (!inviteEmail.trim()) return
    setInviting(true)
    setInviteError('')
    setInviteResult(null)
    try {
      const res = await api.post<{ invite_url: string; email: string; reused: boolean }>(
        '/admin/individual-invites',
        { email: inviteEmail.trim() },
      )
      setInviteResult(res)
    } catch (err) {
      setInviteError(err instanceof Error ? err.message : 'Failed to generate invite')
    } finally {
      setInviting(false)
    }
  }

  async function handleCopyInvite() {
    if (!inviteResult) return
    try {
      await navigator.clipboard.writeText(inviteResult.invite_url)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* Preserve the existing best-effort fallback. */ }
  }

  function closeInvite() {
    setShowInvite(false)
    setInviteEmail('')
    setInviteResult(null)
    setInviteError('')
    setCopied(false)
  }

  async function handleGrant() {
    if (!grantTarget || !grantAmount) return
    const amount = parseInt(grantAmount, 10)
    if (isNaN(amount) || amount <= 0) return
    setGranting(true)
    try {
      await api.post(`/matcha-work/billing/admin/companies/${grantTarget.company_id}/tokens`, {
        tokens: amount,
        description: `Admin grant to individual: ${grantTarget.email}`,
      })
      // Await the refetch before dismissing: closing first leaves the row
      // showing its pre-grant token count for the length of the round-trip,
      // which reads as "the grant didn't work".
      await fetchUsers()
      setGrantTarget(null)
      setGrantAmount('')
    } catch { /* Preserve the existing best-effort fallback. */ }
    setGranting(false)
  }

  async function handleSaveBonus() {
    if (!bonusTarget || bonusAmount === '') return
    const units = parseInt(bonusAmount, 10)
    if (isNaN(units) || units < 0 || units > MAX_BONUS_UNITS) return
    setSavingBonus(true)
    try {
      await api.patch(`/admin/users/${bonusTarget.user_id}/beta-flags`, { [BONUS_KEY]: units })
      await fetchUsers()
      setBonusTarget(null)
      setBonusAmount('')
    } catch { /* Preserve the existing best-effort fallback. */ }
    setSavingBonus(false)
  }

  async function toggleSuspend(u: IndividualUser) {
    const path = u.is_suspended ? 'unsuspend' : 'suspend'
    if (!u.is_suspended && !confirm(`Suspend ${u.email}? They will be locked out.`)) return
    setUsers((prev) => prev.map((x) => (x.user_id === u.user_id ? { ...x, is_suspended: !u.is_suspended } : x)))
    try {
      await api.post(`/admin/users/${u.user_id}/${path}`, {})
    } catch {
      // Revert on failure
      setUsers((prev) => prev.map((x) => (x.user_id === u.user_id ? { ...x, is_suspended: u.is_suspended } : x)))
    }
  }

  async function issuePasswordReset(u: IndividualUser) {
    try {
      const res = await api.post<{ reset_url: string }>(`/admin/users/${u.user_id}/password-reset`, {})
      try { await navigator.clipboard.writeText(res.reset_url) } catch { /* Preserve the existing best-effort fallback. */ }
      alert(`Reset link copied to clipboard. Valid 1 hour:\n\n${res.reset_url}`)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to issue reset link')
    }
  }

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return users.filter((user) => {
      const paid = user.subscription?.status === 'active'
      const comped = user.beta_features?.matcha_work_beta_lite || user.beta_features?.matcha_work_beta_full
      return (!query || user.email.toLowerCase().includes(query) || (user.name ?? '').toLowerCase().includes(query))
        && (status === 'all' || (status === 'suspended' ? user.is_suspended : !user.is_suspended))
        && (plan === 'all' || (plan === 'paid' ? paid : plan === 'comped' ? comped : !paid && !comped))
    }).sort((a, b) => {
      if (sort === 'name') return (a.name || a.email).localeCompare(b.name || b.email) || a.user_id.localeCompare(b.user_id)
      if (sort === 'tokens') return (a.free_tokens_remaining + a.subscription_tokens_remaining) - (b.free_tokens_remaining + b.subscription_tokens_remaining) || a.user_id.localeCompare(b.user_id)
      const date = (a.created_at ? new Date(a.created_at).getTime() : 0) - (b.created_at ? new Date(b.created_at).getTime() : 0)
      return (sort === 'oldest' ? date : -date) || a.user_id.localeCompare(b.user_id)
    })
  }, [users, search, status, plan, sort])
  const pagination = useAdminPagination(filtered, JSON.stringify([search, status, plan, sort]))

  const activeSubscriptions = users.filter((user) => user.subscription?.status === 'active').length
  const comped = users.filter((user) => user.beta_features?.matcha_work_beta_lite || user.beta_features?.matcha_work_beta_full).length
  const suspended = users.filter((user) => user.is_suspended).length
  const tokensRemaining = users.reduce((sum, user) => sum + user.free_tokens_remaining + user.subscription_tokens_remaining, 0)

  if (loading && users.length === 0 && !error) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-zinc-500" size={24} />
      </div>
    )
  }

  return (
    <AdminList>
      {!embedded && (
        <AdminPageHeader title={<>Individual Users</>} description={<>Personal account users ({users.length} total) — the Lite/Pro checkboxes comp the full Werk tier without Stripe</>} />
      )}

      {embedded && <AdminMetricRow items={[
        { label: 'Personal accounts', value: users.length },
        { label: 'Subscriptions', value: activeSubscriptions },
        { label: 'Comped', value: comped },
        { label: 'Suspended', value: suspended },
        { label: 'Tokens remaining', value: formatTokens(tokensRemaining) },
      ]} />}

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative min-w-48 flex-1 sm:max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <AdminInput aria-label="Search personal accounts" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search email or name…" className="py-1.5! pl-9 pr-3 text-xs!" />
        </div>
        <AdminSelect aria-label="Account status" value={status} onChange={(event) => setStatus(event.target.value)} className="py-1.5! text-xs!">
          <option value="all">All statuses</option><option value="active">Active</option><option value="suspended">Suspended</option>
        </AdminSelect>
        <AdminSelect aria-label="Plan filter" value={plan} onChange={(event) => setPlan(event.target.value)} className="py-1.5! text-xs!">
          <option value="all">All plans</option><option value="paid">Paid subscription</option><option value="comped">Comped</option><option value="free">Free</option>
        </AdminSelect>
        <AdminSelect aria-label="Sort personal accounts" value={sort} onChange={(event) => setSort(event.target.value)} className="py-1.5! text-xs!">
          <option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="name">Name A–Z</option><option value="tokens">Lowest token balance</option>
        </AdminSelect>
        <AdminButton onClick={() => setShowInvite(true)} className="gap-1.5 sm:ml-auto" variant="success"><UserPlus size={12} />Generate Signup URL</AdminButton>
      </div>
      {error && <div role="alert" className="mb-3 flex items-center gap-3 text-xs text-red-300">{error}<AdminButton variant="ghost" onClick={fetchUsers}>Retry</AdminButton></div>}
      <AdminPagination pagination={pagination} />
      <AdminTable className="min-w-[880px]">
        <thead><tr>
          <th>Account</th><th>Plan</th><th>Tokens used</th><th>Remaining</th><th title="Comped tier access without Stripe">Comped access</th><th>Joined</th><th className="text-right">Actions</th>
        </tr></thead>
        <tbody>
          {pagination.rows.length === 0 && <tr><td colSpan={7} className="text-center text-zinc-500">{error ? 'Accounts could not be loaded.' : users.length ? 'No users match these filters.' : 'No individual users yet.'}</td></tr>}
          {pagination.rows.map((user) => {
            const pct = user.free_token_limit > 0 ? Math.min(100, (user.free_tokens_used / user.free_token_limit) * 100) : 0
            const low = user.free_tokens_remaining <= 0
            const warn = !low && pct > 80
            return <tr key={user.user_id} className="hover:bg-zinc-800/20">
              <td className="max-w-60">
                <Link to={`/admin/companies/${user.company_id}`} title={user.email} className="block truncate font-medium text-zinc-100 hover:text-zinc-300">{user.email}</Link>
                <div className="mt-0.5 flex items-center gap-2 text-[11px] text-zinc-500"><span className="truncate" title={user.name ?? undefined}>{user.name || '—'}</span>{user.is_suspended && <span className="shrink-0 text-red-300">Suspended</span>}</div>
              </td>
              <td className="whitespace-nowrap">
                {user.subscription ? <>
                  <div className="text-zinc-300">{user.subscription.pack_id} · <span className={user.subscription.status === 'active' ? 'text-zinc-200' : 'text-zinc-500'}>{user.subscription.status}</span></div>
                  <div className="mt-0.5 text-[10px] text-zinc-500">{fmtUsd(user.subscription.amount_cents)}{user.subscription.current_period_end && <> · renews {new Date(user.subscription.current_period_end).toLocaleDateString()}</>}</div>
                </> : user.beta_features?.matcha_work_beta_full ? <span className="admin-badge">Pro · comped</span>
                  : user.beta_features?.matcha_work_beta_lite ? <span className="admin-badge">Lite · comped</span> : <span className="text-zinc-500">Free</span>}
                {bonusUnits(user) > 0 && <div className="mt-0.5 text-[10px] text-zinc-500" title="Extra monthly units for job searches and tasks">+{bonusUnits(user)} task units</div>}
              </td>
              <td className="tabular-nums">
                <span className={low ? 'text-red-400' : warn ? 'text-amber-400' : 'text-zinc-300'}>{formatTokens(user.free_tokens_used)}</span>
                <div className="mt-1 h-1 w-16 overflow-hidden rounded-full bg-zinc-800" title={`${user.free_tokens_used.toLocaleString()} of ${user.free_token_limit.toLocaleString()} free tokens used`}><div className={`h-full rounded-full ${low ? 'bg-red-500' : warn ? 'bg-amber-500' : 'bg-zinc-400'}`} style={{ width: `${pct}%` }} /></div>
              </td>
              <td className="whitespace-nowrap tabular-nums" title="Available free and subscription tokens">
                <span className={low && !user.subscription_tokens_remaining ? 'font-medium text-red-400' : 'text-zinc-300'}>{formatTokens(user.free_tokens_remaining + user.subscription_tokens_remaining)}</span>
                <div className="mt-0.5 text-[10px] text-zinc-500">{formatTokens(user.free_tokens_remaining)} free · {formatTokens(user.subscription_tokens_remaining)} plan</div>
              </td>
              <td className="whitespace-nowrap"><div className="flex items-center gap-3">
                <label className="flex items-center gap-1.5 text-[11px] text-zinc-400" title="Comp full Lite access without Stripe"><input aria-label={`Lite comp for ${user.email}`} type="checkbox" checked={!!user.beta_features?.matcha_work_beta_lite} onChange={(event) => toggleBetaFlag(user.user_id, 'matcha_work_beta_lite', event.target.checked)} className="h-3.5 w-3.5 cursor-pointer accent-emerald-500" />Lite</label>
                <label className="flex items-center gap-1.5 text-[11px] text-zinc-400" title="Comp full Pro access without Stripe"><input aria-label={`Pro comp for ${user.email}`} type="checkbox" checked={!!user.beta_features?.matcha_work_beta_full} onChange={(event) => toggleBetaFlag(user.user_id, 'matcha_work_beta_full', event.target.checked)} className="h-3.5 w-3.5 cursor-pointer accent-emerald-500" />Pro</label>
              </div></td>
              <td className="whitespace-nowrap text-zinc-500" title={user.created_at ?? undefined}>{relTime(user.created_at)}</td>
              <td><div className="flex items-center justify-end gap-2 whitespace-nowrap">
                <Link to={`/admin/companies/${user.company_id}`} className="text-xs text-zinc-400 hover:text-zinc-100" title="Billing, refunds, and account details">Manage</Link>
                <AdminActionMenu label={`Actions for ${user.email}`} items={[
                  { label: 'Grant tokens', onSelect: () => { setGrantTarget(user); setGrantAmount('') } },
                  { label: 'Set extra job searches', onSelect: () => { setBonusTarget(user); setBonusAmount(String(bonusUnits(user))) } },
                  { label: 'Reset password', onSelect: () => issuePasswordReset(user) },
                  { label: user.is_suspended ? 'Unsuspend account' : 'Suspend account', danger: !user.is_suspended, onSelect: () => toggleSuspend(user) },
                  ...(user.subscription ? [{ label: 'Open Stripe subscription', href: `https://dashboard.stripe.com/subscriptions/${user.subscription.stripe_subscription_id}` }] : []),
                ]} />
              </div></td>
            </tr>
          })}
        </tbody>
      </AdminTable>

      {/* Generate signup URL modal */}
      {showInvite && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <AdminCard className="w-full max-w-md">
            <h3 className="text-sm font-semibold text-zinc-100 mb-1">Generate Individual Signup URL</h3>
            <p className="text-xs text-zinc-500 mb-4">
              Creates a one-time matcha-work invite link for an individual account. No email is sent — share the URL manually.
            </p>
            {!inviteResult ? (
              <>
                <label className="block text-[11px] font-medium text-zinc-400 mb-1">Email</label>
                <AdminInput
                  aria-label="Invite email"
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="user@example.com"
                  autoFocus
                  className="mb-3"
                  onKeyDown={(e) => { if (e.key === 'Enter') handleCreateInvite() }}
                />
                {inviteError && (
                  <p className="text-[11px] text-red-400 mb-3">{inviteError}</p>
                )}
                <div className="flex justify-end gap-2">
                  <button
                    onClick={closeInvite}
                    className="px-3 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200"
                  >
                    Cancel
                  </button>
                  <AdminButton
                    onClick={handleCreateInvite}
                    disabled={!inviteEmail.trim() || inviting}
                    className="gap-1.5 disabled:opacity-40" variant="success"
                  >
                    {inviting ? <Loader2 size={12} className="animate-spin" /> : <UserPlus size={12} />}
                    Generate URL
                  </AdminButton>
                </div>
              </>
            ) : (
              <>
                <p className="text-[11px] text-zinc-500 mb-2">
                  Invite for <span className="text-zinc-300">{inviteResult.email}</span>
                  {inviteResult.reused && <span className="ml-2 text-amber-400">(existing pending invite reused)</span>}
                </p>
                <div className="flex items-center gap-2 p-2 rounded-lg border border-zinc-700 bg-zinc-800 mb-4">
                  <code className="flex-1 text-[11px] text-zinc-300 truncate font-mono">{inviteResult.invite_url}</code>
                  <AdminButton
                    onClick={handleCopyInvite}
                    className="shrink-0 gap-1" variant="secondary"
                  >
                    {copied ? <Check size={10} /> : <Copy size={10} />}
                    {copied ? 'Copied' : 'Copy'}
                  </AdminButton>
                </div>
                <div className="flex justify-end">
                  <AdminButton
                    onClick={closeInvite}
                   variant="secondary"
                  >
                    Done
                  </AdminButton>
                </div>
              </>
            )}
          </AdminCard>
        </div>
      )}

      {/* Grant tokens modal */}
      {grantTarget && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <AdminCard className="w-full max-w-sm">
            <h3 className="text-sm font-semibold text-zinc-100 mb-1">Grant Tokens</h3>
            <p className="text-xs text-zinc-500 mb-4">{grantTarget.email}</p>
            <p className="text-[11px] text-zinc-500 mb-3">
              Current: {formatTokens(grantTarget.free_tokens_remaining)} remaining of {formatTokens(grantTarget.free_token_limit)}
            </p>
            <div className="flex gap-2 mb-4">
              {[100_000, 500_000, 1_000_000, 5_000_000].map((amt) => (
                <button
                  key={amt}
                  onClick={() => setGrantAmount(String(amt))}
                  className={`px-2 py-1 rounded text-[10px] font-medium transition-colors ${
                    grantAmount === String(amt) ? 'bg-emerald-700 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  +{formatTokens(amt)}
                </button>
              ))}
            </div>
            <AdminInput
              aria-label="Token grant amount"
              value={grantAmount}
              onChange={(e) => setGrantAmount(e.target.value.replace(/\D/g, ''))}
              placeholder="Custom amount..."
              className="mb-4"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setGrantTarget(null)}
                className="px-3 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200"
              >
                Cancel
              </button>
              <AdminButton
                onClick={handleGrant}
                disabled={!grantAmount || granting}
                className="gap-1.5 disabled:opacity-40" variant="success"
              >
                {granting ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
                Grant {grantAmount ? formatTokens(parseInt(grantAmount, 10) || 0) : ''}
              </AdminButton>
            </div>
          </AdminCard>
        </div>
      )}

      {/* Extra job searches modal */}
      {bonusTarget && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <AdminCard className="w-full max-w-sm">
            <h3 className="text-sm font-semibold text-zinc-100 mb-1">Extra Job Searches</h3>
            <p className="text-xs text-zinc-500 mb-4">{bonusTarget.email}</p>
            <p className="text-[11px] text-zinc-500 mb-3">
              Added to their plan's monthly allowance of task units (Pro 60, Business 150), every month, until set back to 0.
              A job search costs 5 units, so 50 units is 10 more searches. They need a Pro plan or a Pro comp.
            </p>
            <div className="flex gap-2 mb-4">
              {BONUS_PRESETS.map((units) => (
                <button
                  key={units}
                  onClick={() => setBonusAmount(String(units))}
                  className={`px-2 py-1 rounded text-[10px] font-medium transition-colors ${
                    bonusAmount === String(units) ? 'bg-emerald-700 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  {units} units · {units / 5} searches
                </button>
              ))}
            </div>
            <AdminInput
              aria-label="Extra task units"
              value={bonusAmount}
              onChange={(e) => setBonusAmount(e.target.value.replace(/\D/g, '').slice(0, 4))}
              placeholder={`Units, 0 to ${MAX_BONUS_UNITS}`}
              className="mb-4"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => { setBonusTarget(null); setBonusAmount('') }}
                className="px-3 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200"
              >
                Cancel
              </button>
              <AdminButton
                onClick={handleSaveBonus}
                disabled={bonusAmount === '' || parseInt(bonusAmount, 10) > MAX_BONUS_UNITS || savingBonus}
                className="gap-1.5 disabled:opacity-40" variant="success"
              >
                {savingBonus ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
                Save
              </AdminButton>
            </div>
          </AdminCard>
        </div>
      )}
    </AdminList>
  )
}
