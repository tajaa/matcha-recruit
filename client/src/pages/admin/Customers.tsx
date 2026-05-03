import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, Search, Shield, KeyRound } from 'lucide-react'
import { api } from '../../api/client'

// ── Types ────────────────────────────────────────────────────────────────────

type Subscription = {
  pack_id: string
  status: string
  amount_cents: number
  stripe_subscription_id: string
  stripe_customer_id: string
  current_period_end: string | null
  canceled_at: string | null
}

type Registration = {
  id: string
  company_name: string
  industry: string | null
  company_size: string | null
  owner_user_id: string | null
  owner_email: string
  owner_name: string
  status: string
  created_at: string
  signup_source: string | null
  is_personal: boolean
  is_suspended: boolean
  deleted_at: string | null
  subscription: Subscription | null
}

type Individual = {
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
  subscription?: Subscription | null
}

type Tab = 'all' | 'free' | 'lite' | 'platform' | 'personal'

const TAB_DEFS: { id: Tab; label: string; help: string }[] = [
  { id: 'all', label: 'All', help: 'Every customer in the system.' },
  { id: 'free', label: 'Free', help: 'resources_free signups — no paid features, audit + templates only.' },
  { id: 'lite', label: 'Matcha Lite', help: 'Stripe-billed self-serve bundle (IR + Resources).' },
  { id: 'platform', label: 'Platform', help: 'Bespoke / sales-led companies on full feature set.' },
  { id: 'personal', label: 'Matcha Work Personal', help: 'role=individual, personal workspace, optional Stripe sub.' },
]

const TIER_BADGE: Record<Exclude<Tab, 'all'>, string> = {
  free: 'border-zinc-600 bg-zinc-700/30 text-zinc-300',
  lite: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  platform: 'border-violet-500/40 bg-violet-500/10 text-violet-300',
  personal: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
}

const TIER_LABEL: Record<Exclude<Tab, 'all'>, string> = {
  free: 'Free',
  lite: 'Lite',
  platform: 'Platform',
  personal: 'Personal',
}

function tierFromRegistration(r: Registration): Exclude<Tab, 'all'> {
  if (r.is_personal) return 'personal'
  if (r.signup_source === 'resources_free') return 'free'
  if (r.signup_source === 'matcha_lite') return 'lite'
  return 'platform'
}

function fmtUsd(cents: number) {
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function relTime(iso: string | null) {
  if (!iso) return '—'
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (d === 0) return 'Today'
  if (d === 1) return 'Yesterday'
  return `${d}d ago`
}

function fmtTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`
  return String(n)
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function Customers() {
  const [tab, setTab] = useState<Tab>('all')
  const [search, setSearch] = useState('')
  const [registrations, setRegistrations] = useState<Registration[] | null>(null)
  const [individuals, setIndividuals] = useState<Individual[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [resetUrl, setResetUrl] = useState<{ email: string; url: string } | null>(null)

  async function refresh() {
    setBusy(true)
    try {
      const [regs, indis] = await Promise.all([
        api.get<{ registrations: Registration[]; total: number }>('/admin/business-registrations').catch(() => ({ registrations: [], total: 0 })),
        api.get<Individual[]>('/matcha-work/billing/admin/individuals').catch(() => []),
      ])
      setRegistrations(regs.registrations)
      setIndividuals(indis)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { refresh() }, [])

  const tabRows = useMemo(() => {
    if (tab === 'personal') return individuals
    if (!registrations) return null
    if (tab === 'all') return registrations
    return registrations.filter((r) => tierFromRegistration(r) === tab)
  }, [tab, registrations, individuals])

  const counts = useMemo(() => {
    const c = { all: 0, free: 0, lite: 0, platform: 0, personal: individuals?.length ?? 0 }
    if (registrations) {
      c.all = registrations.length
      for (const r of registrations) {
        const t = tierFromRegistration(r)
        if (t !== 'personal') c[t] += 1
      }
    }
    return c
  }, [registrations, individuals])

  // Lifecycle quick-actions
  async function suspendUser(userId: string | null | undefined, currentlySuspended: boolean | undefined) {
    if (!userId) return
    const path = currentlySuspended ? 'unsuspend' : 'suspend'
    if (!currentlySuspended && !confirm('Suspend this user? They will be locked out.')) return
    try {
      await api.post(`/admin/users/${userId}/${path}`, {})
      await refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed')
    }
  }

  async function passwordReset(userId: string | null | undefined, email: string) {
    if (!userId) return
    try {
      const res = await api.post<{ reset_url: string }>(`/admin/users/${userId}/password-reset`, {})
      try { await navigator.clipboard.writeText(res.reset_url) } catch {}
      setResetUrl({ email, url: res.reset_url })
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed')
    }
  }

  async function cancelSub(companyId: string, immediate: boolean) {
    if (!confirm(immediate ? 'Cancel subscription immediately?' : 'Cancel subscription at period end?')) return
    try {
      const qs = immediate ? '?immediate=true' : ''
      await api.post(`/admin/companies/${companyId}/cancel-subscription${qs}`, {})
      await refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed')
    }
  }

  async function softDelete(companyId: string) {
    if (!confirm('Soft-delete? Customer is locked out, rows persist for audit.')) return
    try {
      await api.delete(`/admin/companies/${companyId}`)
      await refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed')
    }
  }

  async function restore(companyId: string) {
    try {
      await api.post(`/admin/companies/${companyId}/restore`, {})
      await refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed')
    }
  }

  const tabHelp = TAB_DEFS.find((t) => t.id === tab)?.help

  return (
    <div>
      <div className="flex items-end justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Customers</h1>
          <p className="text-sm text-zinc-500 mt-1">{tabHelp}</p>
        </div>
        <button
          onClick={refresh}
          disabled={busy}
          className="text-xs px-3 py-1.5 rounded-lg bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:opacity-40"
        >
          {busy ? <Loader2 className="w-3 h-3 animate-spin inline" /> : 'Refresh'}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 border-b border-zinc-800 mb-4">
        {TAB_DEFS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`relative px-4 py-2 text-xs font-medium transition-colors -mb-px ${
              tab === t.id
                ? 'text-zinc-100 border-b-2 border-emerald-500'
                : 'text-zinc-500 hover:text-zinc-300 border-b-2 border-transparent'
            }`}
          >
            {t.label}
            <span className="ml-2 text-[10px] text-zinc-600 font-mono">{counts[t.id]}</span>
          </button>
        ))}
      </div>

      {/* Search */}
      <div className="relative mb-4 max-w-xs">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by email or company…"
          className="w-full pl-9 pr-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-600"
        />
      </div>

      {/* Reset URL toast */}
      {resetUrl && (
        <div className="mb-4 p-3 rounded-lg border border-emerald-700/40 bg-emerald-900/20 flex items-start justify-between gap-3">
          <div className="text-xs">
            <div className="text-emerald-300 font-medium">Reset link copied for {resetUrl.email} (1 hour)</div>
            <code className="block mt-1 text-[10px] break-all text-emerald-100">{resetUrl.url}</code>
          </div>
          <button
            onClick={() => setResetUrl(null)}
            className="text-[11px] text-emerald-300 hover:text-emerald-100 shrink-0"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Table */}
      {tabRows === null ? (
        <div className="flex items-center justify-center h-32">
          <Loader2 className="w-5 h-5 text-zinc-500 animate-spin" />
        </div>
      ) : tab === 'personal' ? (
        <PersonalTable
          rows={(individuals ?? []).filter((u) => matchSearch(u.email, u.name, search))}
          onSuspend={(u) => suspendUser(u.user_id, u.is_suspended)}
          onReset={(u) => passwordReset(u.user_id, u.email)}
          onCancel={(u) => cancelSub(u.company_id, true)}
        />
      ) : (
        <RegistrationTable
          tab={tab}
          rows={(tabRows as Registration[]).filter((r) => matchSearch(r.owner_email, r.company_name, search))}
          onSuspend={(r) => suspendUser(r.owner_user_id, r.is_suspended)}
          onReset={(r) => passwordReset(r.owner_user_id, r.owner_email)}
          onCancel={(r) => cancelSub(r.id, true)}
          onCancelAtEnd={(r) => cancelSub(r.id, false)}
          onSoftDelete={(r) => softDelete(r.id)}
          onRestore={(r) => restore(r.id)}
        />
      )}
    </div>
  )
}

function matchSearch(a: string, b: string | null, q: string) {
  if (!q.trim()) return true
  const needle = q.toLowerCase()
  return a.toLowerCase().includes(needle) || (b ?? '').toLowerCase().includes(needle)
}

// ── Registration table (Free / Lite / Platform / All) ────────────────────────

function RegistrationTable({
  tab,
  rows,
  onSuspend,
  onReset,
  onCancel,
  onCancelAtEnd,
  onSoftDelete,
  onRestore,
}: {
  tab: Tab
  rows: Registration[]
  onSuspend: (r: Registration) => void
  onReset: (r: Registration) => void
  onCancel: (r: Registration) => void
  onCancelAtEnd: (r: Registration) => void
  onSoftDelete: (r: Registration) => void
  onRestore: (r: Registration) => void
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-zinc-500">No customers in this tab.</p>
  }

  // Show columns appropriate to the tier; All shows the union.
  const showTier = tab === 'all'
  const showSub = tab === 'lite' || tab === 'all'
  const showStatus = tab === 'platform' || tab === 'all'

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-800">
      <table className="w-full text-xs">
        <thead className="bg-zinc-900/60 text-zinc-500 uppercase tracking-widest text-[10px]">
          <tr>
            <th className="text-left px-4 py-2.5 font-medium">Company / Email</th>
            {showTier && <th className="text-left px-4 py-2.5 font-medium">Tier</th>}
            <th className="text-left px-4 py-2.5 font-medium">Joined</th>
            {showStatus && <th className="text-left px-4 py-2.5 font-medium">Status</th>}
            {showSub && <th className="text-left px-4 py-2.5 font-medium">Subscription</th>}
            <th className="text-left px-4 py-2.5 font-medium">Account</th>
            <th className="text-left px-4 py-2.5 font-medium w-[280px]">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const tier = tierFromRegistration(r)
            const isDeleted = !!r.deleted_at
            return (
              <tr key={r.id} className="border-t border-zinc-800/50 hover:bg-zinc-800/20">
                <td className="px-4 py-3">
                  <Link to={`/admin/companies/${r.id}`} className="font-medium text-zinc-100 hover:text-emerald-400">
                    {r.company_name}
                  </Link>
                  <div className="text-[10px] text-zinc-500">{r.owner_email}</div>
                </td>
                {showTier && (
                  <td className="px-4 py-3">
                    <span className={`inline-block text-[10px] px-1.5 py-0.5 rounded border ${TIER_BADGE[tier]}`}>
                      {TIER_LABEL[tier]}
                    </span>
                  </td>
                )}
                <td className="px-4 py-3 text-zinc-400">{relTime(r.created_at)}</td>
                {showStatus && (
                  <td className="px-4 py-3">
                    <StatusBadge status={r.status} />
                  </td>
                )}
                {showSub && (
                  <td className="px-4 py-3">
                    {r.subscription ? (
                      <div className="flex flex-col gap-0.5">
                        <span className="text-zinc-300">
                          {r.subscription.pack_id} ·{' '}
                          <span className={r.subscription.status === 'active' ? 'text-emerald-400' : 'text-zinc-500'}>
                            {r.subscription.status}
                          </span>
                        </span>
                        <span className="text-[10px] text-zinc-500">
                          {fmtUsd(r.subscription.amount_cents)}
                          {r.subscription.current_period_end && (
                            <> · renews {new Date(r.subscription.current_period_end).toLocaleDateString()}</>
                          )}
                        </span>
                      </div>
                    ) : (
                      <span className="text-zinc-600">—</span>
                    )}
                  </td>
                )}
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {r.is_suspended && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded border border-red-500/40 bg-red-500/10 text-red-300">
                        Suspended
                      </span>
                    )}
                    {isDeleted && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded border border-zinc-700 bg-zinc-800 text-zinc-400">
                        Deleted
                      </span>
                    )}
                    {!r.is_suspended && !isDeleted && (
                      <span className="text-[10px] text-zinc-600">Active</span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {!isDeleted && (
                      <>
                        <ActionBtn icon={Shield} label={r.is_suspended ? 'Unsus' : 'Suspend'} onClick={() => onSuspend(r)} />
                        <ActionBtn icon={KeyRound} label="Reset" onClick={() => onReset(r)} disabled={!r.owner_user_id} />
                        {r.subscription && r.subscription.status === 'active' && (
                          <>
                            <ActionBtn label="Cancel ↘" onClick={() => onCancelAtEnd(r)} />
                            <ActionBtn label="Cancel now" tone="danger" onClick={() => onCancel(r)} />
                          </>
                        )}
                        <Link
                          to={`/admin/companies/${r.id}`}
                          className="text-[10px] px-2 py-1 rounded bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                        >
                          More →
                        </Link>
                      </>
                    )}
                    {!isDeleted ? (
                      <ActionBtn label="Delete" tone="danger" onClick={() => onSoftDelete(r)} />
                    ) : (
                      <ActionBtn label="Restore" tone="success" onClick={() => onRestore(r)} />
                    )}
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Personal table ───────────────────────────────────────────────────────────

function PersonalTable({
  rows,
  onSuspend,
  onReset,
  onCancel,
}: {
  rows: Individual[]
  onSuspend: (u: Individual) => void
  onReset: (u: Individual) => void
  onCancel: (u: Individual) => void
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-zinc-500">No personal users yet.</p>
  }
  return (
    <div className="overflow-hidden rounded-xl border border-zinc-800">
      <table className="w-full text-xs">
        <thead className="bg-zinc-900/60 text-zinc-500 uppercase tracking-widest text-[10px]">
          <tr>
            <th className="text-left px-4 py-2.5 font-medium">Email</th>
            <th className="text-left px-4 py-2.5 font-medium">Joined</th>
            <th className="text-left px-4 py-2.5 font-medium">Subscription</th>
            <th className="text-left px-4 py-2.5 font-medium">Tokens</th>
            <th className="text-left px-4 py-2.5 font-medium">Account</th>
            <th className="text-left px-4 py-2.5 font-medium w-[280px]">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((u) => (
            <tr key={u.user_id} className="border-t border-zinc-800/50 hover:bg-zinc-800/20">
              <td className="px-4 py-3 text-zinc-200">
                {u.email}
                {u.name && <div className="text-[10px] text-zinc-500">{u.name}</div>}
              </td>
              <td className="px-4 py-3 text-zinc-400">{relTime(u.created_at)}</td>
              <td className="px-4 py-3">
                {u.subscription ? (
                  <div className="flex flex-col gap-0.5">
                    <span className="text-zinc-300">
                      {u.subscription.pack_id} ·{' '}
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
                  </div>
                ) : (
                  <span className="text-zinc-600">Free</span>
                )}
              </td>
              <td className="px-4 py-3 text-zinc-400">
                {fmtTokens(u.free_tokens_used)} / {fmtTokens(u.free_token_limit)}
              </td>
              <td className="px-4 py-3">
                {u.is_suspended ? (
                  <span className="text-[10px] px-1.5 py-0.5 rounded border border-red-500/40 bg-red-500/10 text-red-300">
                    Suspended
                  </span>
                ) : (
                  <span className="text-[10px] text-zinc-600">Active</span>
                )}
              </td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  <ActionBtn icon={Shield} label={u.is_suspended ? 'Unsus' : 'Suspend'} onClick={() => onSuspend(u)} />
                  <ActionBtn icon={KeyRound} label="Reset" onClick={() => onReset(u)} />
                  {u.subscription && u.subscription.status === 'active' && (
                    <ActionBtn label="Cancel sub" tone="danger" onClick={() => onCancel(u)} />
                  )}
                  <Link
                    to={`/admin/companies/${u.company_id}`}
                    className="text-[10px] px-2 py-1 rounded bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                  >
                    Tokens / Refund →
                  </Link>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Tiny helpers ─────────────────────────────────────────────────────────────

function ActionBtn({
  icon: Icon,
  label,
  onClick,
  tone,
  disabled,
}: {
  icon?: React.ElementType
  label: string
  onClick: () => void
  tone?: 'danger' | 'success'
  disabled?: boolean
}) {
  const cls =
    tone === 'danger'
      ? 'bg-red-900/40 text-red-200 hover:bg-red-900/60'
      : tone === 'success'
      ? 'bg-emerald-700 text-white hover:bg-emerald-600'
      : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors disabled:opacity-40 ${cls}`}
    >
      {Icon && <Icon size={10} />}
      {label}
    </button>
  )
}

function StatusBadge({ status }: { status: string }) {
  if (!status || status === 'approved')
    return <span className="text-[10px] px-1.5 py-0.5 rounded border border-emerald-500/40 bg-emerald-500/10 text-emerald-300">Approved</span>
  if (status === 'pending')
    return <span className="text-[10px] px-1.5 py-0.5 rounded border border-amber-500/40 bg-amber-500/10 text-amber-300">Pending</span>
  return <span className="text-[10px] px-1.5 py-0.5 rounded border border-red-500/40 bg-red-500/10 text-red-300">{status}</span>
}
