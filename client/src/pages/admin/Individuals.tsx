import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, Search, Zap, Plus, UserPlus, Copy, Check, Shield, KeyRound } from 'lucide-react'
import { api } from '../../api/client'

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
  beta_features?: Record<string, boolean>
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

export default function Individuals() {
  const [users, setUsers] = useState<IndividualUser[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [grantTarget, setGrantTarget] = useState<IndividualUser | null>(null)
  const [grantAmount, setGrantAmount] = useState('')
  const [granting, setGranting] = useState(false)
  const [showInvite, setShowInvite] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteResult, setInviteResult] = useState<{ invite_url: string; email: string; reused: boolean } | null>(null)
  const [inviteError, setInviteError] = useState('')
  const [inviting, setInviting] = useState(false)
  const [copied, setCopied] = useState(false)

  function fetchUsers() {
    api.get<IndividualUser[]>('/matcha-work/billing/admin/individuals')
      .then(setUsers)
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchUsers() }, [])

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
    } catch {}
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
      // Refresh list
      const updated = await api.get<IndividualUser[]>('/matcha-work/billing/admin/individuals')
      setUsers(updated)
      setGrantTarget(null)
      setGrantAmount('')
    } catch {}
    setGranting(false)
  }

  async function toggleSuspend(u: IndividualUser) {
    const path = u.is_suspended ? 'unsuspend' : 'suspend'
    if (u.is_suspended === false && !confirm(`Suspend ${u.email}? They will be locked out.`)) return
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
      try { await navigator.clipboard.writeText(res.reset_url) } catch {}
      alert(`Reset link copied to clipboard. Valid 1 hour:\n\n${res.reset_url}`)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to issue reset link')
    }
  }

  const filtered = users.filter((u) => {
    if (!search) return true
    const q = search.toLowerCase()
    return u.email.toLowerCase().includes(q) || (u.name || '').toLowerCase().includes(q)
  })

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-zinc-500" size={24} />
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Individual Users</h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            Personal account users ({users.length} total)
          </p>
        </div>
        <button
          onClick={() => setShowInvite(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-700 text-white text-xs font-medium hover:bg-emerald-600 transition-colors"
        >
          <UserPlus size={12} />
          Generate Signup URL
        </button>
      </div>

      {/* Search */}
      <div className="relative mb-4 max-w-xs">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by email or name..."
          className="w-full pl-9 pr-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-600"
        />
      </div>

      {/* Table */}
      <div className="rounded-xl border border-zinc-800 overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-zinc-900/80 border-b border-zinc-800">
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400">Email</th>
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400">Name</th>
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400">Joined</th>
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400">Subscription</th>
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400">Tokens Used</th>
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400">Remaining</th>
              <th className="text-center px-4 py-2.5 font-medium text-zinc-400">Beta Lite</th>
              <th className="text-center px-4 py-2.5 font-medium text-zinc-400">Beta Full</th>
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400 w-32">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-zinc-500">
                  {search ? 'No users match your search.' : 'No individual users yet.'}
                </td>
              </tr>
            )}
            {filtered.map((u) => {
              const pct = u.free_token_limit > 0 ? Math.min(100, (u.free_tokens_used / u.free_token_limit) * 100) : 0
              const low = u.free_tokens_remaining <= 0
              const warn = !low && pct > 80
              return (
                <tr key={u.user_id} className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                  <td className="px-4 py-3 text-zinc-200">
                    {u.email}
                    {u.is_suspended && (
                      <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded border border-red-500/40 bg-red-500/10 text-red-300">
                        Suspended
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-zinc-400">{u.name || '--'}</td>
                  <td className="px-4 py-3 text-zinc-500">{relTime(u.created_at)}</td>
                  <td className="px-4 py-3">
                    {u.subscription ? (
                      <div className="flex flex-col gap-0.5">
                        <span className="text-zinc-300">
                          {u.subscription.pack_id} <span className="text-zinc-500">·</span>{' '}
                          <span className={u.subscription.status === 'active' ? 'text-emerald-400' : 'text-zinc-500'}>
                            {u.subscription.status}
                          </span>
                        </span>
                        <span className="text-[10px] text-zinc-500">
                          {fmtUsd(u.subscription.amount_cents)}
                          {u.subscription.current_period_end && (
                            <> · renews {new Date(u.subscription.current_period_end).toLocaleDateString()}</>
                          )}
                        </span>
                        <a
                          href={`https://dashboard.stripe.com/subscriptions/${u.subscription.stripe_subscription_id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[10px] text-emerald-400 hover:text-emerald-300"
                        >
                          Stripe →
                        </a>
                      </div>
                    ) : (
                      <span className="text-zinc-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${low ? 'bg-red-500' : warn ? 'bg-amber-500' : 'bg-emerald-500'}`}
                          style={{ width: `${Math.min(pct, 100)}%` }}
                        />
                      </div>
                      <span className={`${low ? 'text-red-400' : warn ? 'text-amber-400' : 'text-zinc-400'}`}>
                        {formatTokens(u.free_tokens_used)}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={low ? 'text-red-400 font-medium' : 'text-zinc-400'}>
                      {formatTokens(u.free_tokens_remaining)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <input
                      type="checkbox"
                      checked={!!u.beta_features?.matcha_work_beta_lite}
                      onChange={(e) => toggleBetaFlag(u.user_id, 'matcha_work_beta_lite', e.target.checked)}
                      className="accent-emerald-500 w-3.5 h-3.5 cursor-pointer"
                    />
                  </td>
                  <td className="px-4 py-3 text-center">
                    <input
                      type="checkbox"
                      checked={!!u.beta_features?.matcha_work_beta_full}
                      onChange={(e) => toggleBetaFlag(u.user_id, 'matcha_work_beta_full', e.target.checked)}
                      className="accent-emerald-500 w-3.5 h-3.5 cursor-pointer"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <button
                        onClick={() => { setGrantTarget(u); setGrantAmount('') }}
                        className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors"
                        title="Grant tokens"
                      >
                        <Plus size={10} />
                        Tokens
                      </button>
                      <button
                        onClick={() => issuePasswordReset(u)}
                        className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors"
                        title="Issue 1h password reset link"
                      >
                        <KeyRound size={10} />
                        Reset
                      </button>
                      <button
                        onClick={() => toggleSuspend(u)}
                        className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors ${
                          u.is_suspended
                            ? 'bg-emerald-900/40 text-emerald-300 hover:bg-emerald-900/60'
                            : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'
                        }`}
                        title={u.is_suspended ? 'Unsuspend' : 'Suspend'}
                      >
                        <Shield size={10} />
                        {u.is_suspended ? 'Unsuspend' : 'Suspend'}
                      </button>
                      <Link
                        to={`/admin/companies/${u.company_id}`}
                        className="text-[10px] text-zinc-500 hover:text-zinc-300 underline"
                        title="Open company detail for billing/refund/cancel"
                      >
                        Manage →
                      </Link>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Generate signup URL modal */}
      {showInvite && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 w-full max-w-md">
            <h3 className="text-sm font-semibold text-zinc-100 mb-1">Generate Individual Signup URL</h3>
            <p className="text-xs text-zinc-500 mb-4">
              Creates a one-time matcha-work invite link for an individual account. No email is sent — share the URL manually.
            </p>
            {!inviteResult ? (
              <>
                <label className="block text-[11px] font-medium text-zinc-400 mb-1">Email</label>
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="user@example.com"
                  autoFocus
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-600 mb-3"
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
                  <button
                    onClick={handleCreateInvite}
                    disabled={!inviteEmail.trim() || inviting}
                    className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-emerald-700 text-white text-xs font-medium hover:bg-emerald-600 disabled:opacity-40 transition-colors"
                  >
                    {inviting ? <Loader2 size={12} className="animate-spin" /> : <UserPlus size={12} />}
                    Generate URL
                  </button>
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
                  <button
                    onClick={handleCopyInvite}
                    className="shrink-0 flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium bg-zinc-700 text-zinc-200 hover:bg-zinc-600 transition-colors"
                  >
                    {copied ? <Check size={10} /> : <Copy size={10} />}
                    {copied ? 'Copied' : 'Copy'}
                  </button>
                </div>
                <div className="flex justify-end">
                  <button
                    onClick={closeInvite}
                    className="px-4 py-1.5 rounded-lg bg-zinc-800 border border-zinc-700 text-xs text-zinc-300 hover:bg-zinc-700"
                  >
                    Done
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Grant tokens modal */}
      {grantTarget && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 w-full max-w-sm">
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
            <input
              value={grantAmount}
              onChange={(e) => setGrantAmount(e.target.value.replace(/\D/g, ''))}
              placeholder="Custom amount..."
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-600 mb-4"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setGrantTarget(null)}
                className="px-3 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200"
              >
                Cancel
              </button>
              <button
                onClick={handleGrant}
                disabled={!grantAmount || granting}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-emerald-700 text-white text-xs font-medium hover:bg-emerald-600 disabled:opacity-40 transition-colors"
              >
                {granting ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
                Grant {grantAmount ? formatTokens(parseInt(grantAmount, 10) || 0) : ''}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
