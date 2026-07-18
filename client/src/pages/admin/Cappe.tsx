import { Fragment, useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, ExternalLink } from 'lucide-react'
import { Input } from '../../components/ui'
import { api } from '../../api/client'
import { cappeSiteHost } from '../../cappe/host'

type CappeSite = {
  id: string
  name: string
  slug: string
  subdomain: string | null
  custom_domain: string | null
  status: string
  page_count: number
  order_count: number
  revenue_cents: number
  created_at: string | null
  published_at: string | null
}

type CappeAccount = {
  id: string
  email: string
  name: string | null
  plan: string
  status: string
  account_type: string
  created_at: string | null
  site_count: number
  published_count: number
  order_count: number
  revenue_cents: number
  sites: CappeSite[]
}

type CappeTotals = {
  account_count: number
  plan_counts: Record<string, number>
  site_count: number
  published_count: number
  order_count: number
  revenue_cents: number
}

type CappeListResponse = {
  accounts: CappeAccount[]
  totals: CappeTotals
}

type PlanFilter = 'all' | 'free' | 'hosting' | 'pro' | 'business'

const PLAN_LABEL: Record<Exclude<PlanFilter, 'all'>, string> = {
  free: 'Free',
  hosting: 'Hosting',
  pro: 'Pro',
  business: 'Business',
}

const PLAN_BADGE_CLASS: Record<string, string> = {
  free: 'border-zinc-600 bg-zinc-700/30 text-zinc-300',
  hosting: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
  pro: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  business: 'border-violet-500/40 bg-violet-500/10 text-violet-300',
}

function PlanBadge({ plan }: { plan: string }) {
  const cls = PLAN_BADGE_CLASS[plan] ?? PLAN_BADGE_CLASS.free
  const label = PLAN_LABEL[plan as Exclude<PlanFilter, 'all'>] ?? plan
  return (
    <span className={`inline-block text-[10px] px-1.5 py-0.5 rounded border ${cls}`}>
      {label}
    </span>
  )
}

function statusBadgeClass(status: string) {
  if (status === 'active' || status === 'published') return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
  if (status === 'suspended') return 'border-red-500/40 bg-red-500/10 text-red-300'
  if (status === 'draft') return 'border-amber-500/40 bg-amber-500/10 text-amber-300'
  return 'border-zinc-600 bg-zinc-700/30 text-zinc-400'
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block text-[10px] px-1.5 py-0.5 rounded border capitalize ${statusBadgeClass(status)}`}>
      {status}
    </span>
  )
}

const money = (cents: number) =>
  `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`

const fmtDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'

function siteUrl(s: CappeSite): string | null {
  if (!s.custom_domain && !s.subdomain && !s.slug) return null
  return `https://${cappeSiteHost(s)}`
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-3">
      <p className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-zinc-100">{value}</p>
    </div>
  )
}

export default function Cappe() {
  const [accounts, setAccounts] = useState<CappeAccount[]>([])
  const [totals, setTotals] = useState<CappeTotals | null>(null)
  const [plan, setPlan] = useState<PlanFilter>('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  useEffect(() => {
    setLoading(true)
    api.get<CappeListResponse>('/admin/cappe/accounts')
      .then((res) => {
        setAccounts(res.accounts)
        setTotals(res.totals)
      })
      .catch(() => {
        setAccounts([])
        setTotals(null)
      })
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return accounts.filter((a) => {
      if (plan !== 'all' && a.plan !== plan) return false
      if (!q) return true
      return (
        a.email.toLowerCase().includes(q) ||
        (a.name?.toLowerCase().includes(q) ?? false) ||
        a.sites.some((s) => s.name.toLowerCase().includes(q) || s.slug.toLowerCase().includes(q))
      )
    })
  }, [accounts, plan, search])

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div>
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100">Cappe</h1>
        <p className="mt-2 text-sm text-zinc-500">
          Website-builder signups — accounts, plans, sites and revenue.
        </p>
      </div>

      {/* Summary */}
      {totals && (
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <Stat label="Accounts" value={totals.account_count} />
          <Stat label="Sites" value={totals.site_count} />
          <Stat label="Published" value={totals.published_count} />
          <Stat label="Orders" value={totals.order_count} />
          <Stat label="Revenue" value={money(totals.revenue_cents)} />
        </div>
      )}

      {/* Filters */}
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Input
          label=""
          placeholder="Search email, name or site..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <div className="flex items-center gap-1 ml-auto">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500 mr-2">Plan</span>
          {(['all', 'free', 'hosting', 'pro', 'business'] as const).map((p) => {
            const count = p === 'all' ? totals?.account_count : totals?.plan_counts[p]
            return (
              <button
                key={p}
                onClick={() => setPlan(p)}
                className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
                  plan === p
                    ? 'bg-emerald-500 text-zinc-950 font-medium'
                    : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
                }`}
              >
                {p === 'all' ? 'All' : PLAN_LABEL[p]}
                {count != null && <span className="ml-1.5 opacity-70">{count}</span>}
              </button>
            )
          })}
        </div>
      </div>

      {/* Table */}
      <div className="mt-6">
        {loading ? (
          <p className="text-sm text-zinc-500">Loading...</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-zinc-500">No Cappe accounts found.</p>
        ) : (
          <div className="overflow-hidden rounded-xl border border-zinc-800">
            <table className="w-full text-sm text-left">
              <thead className="bg-zinc-900/50 text-zinc-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Account</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Plan</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium text-right">Sites</th>
                  <th className="px-4 py-3 font-medium text-right">Orders</th>
                  <th className="px-4 py-3 font-medium text-right">Revenue</th>
                  <th className="px-4 py-3 font-medium">Joined</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {filtered.map((a) => {
                  const isOpen = expanded.has(a.id)
                  return (
                    <Fragment key={a.id}>
                      <tr
                        className="cursor-pointer text-zinc-300 hover:bg-zinc-900/40"
                        onClick={() => a.site_count > 0 && toggle(a.id)}
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            {a.site_count > 0 ? (
                              isOpen ? (
                                <ChevronDown className="h-4 w-4 shrink-0 text-zinc-500" />
                              ) : (
                                <ChevronRight className="h-4 w-4 shrink-0 text-zinc-500" />
                              )
                            ) : (
                              <span className="h-4 w-4 shrink-0" />
                            )}
                            <div>
                              <p className="font-medium text-zinc-100">{a.name || a.email}</p>
                              {a.name && <p className="text-xs text-zinc-500">{a.email}</p>}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-block text-[10px] px-1.5 py-0.5 rounded border ${
                            a.account_type === 'personal'
                              ? 'border-sky-500/40 bg-sky-500/10 text-sky-300'
                              : 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                          }`}>
                            {a.account_type === 'personal' ? 'Solo' : 'Business'}
                          </span>
                        </td>
                        <td className="px-4 py-3"><PlanBadge plan={a.plan} /></td>
                        <td className="px-4 py-3"><StatusBadge status={a.status} /></td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          {a.site_count}
                          {a.published_count > 0 && (
                            <span className="text-xs text-emerald-400"> · {a.published_count} live</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums">{a.order_count}</td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          {a.revenue_cents > 0 ? money(a.revenue_cents) : '—'}
                        </td>
                        <td className="px-4 py-3 text-zinc-400">{fmtDate(a.created_at)}</td>
                      </tr>
                      {isOpen && a.sites.map((s) => {
                        const url = siteUrl(s)
                        return (
                          <tr key={s.id} className="bg-zinc-950/40 text-zinc-400">
                            <td className="px-4 py-2.5 pl-12">
                              <div className="flex items-center gap-2">
                                <span className="text-zinc-200">{s.name}</span>
                                {url && (
                                  <a
                                    href={url}
                                    target="_blank"
                                    rel="noreferrer"
                                    onClick={(e) => e.stopPropagation()}
                                    className="text-zinc-500 hover:text-emerald-400"
                                    title={url}
                                  >
                                    <ExternalLink className="h-3.5 w-3.5" />
                                  </a>
                                )}
                              </div>
                              <p className="text-xs text-zinc-600">/{s.slug} · {s.page_count} pages</p>
                            </td>
                            <td className="px-4 py-2.5" colSpan={3}><StatusBadge status={s.status} /></td>
                            <td className="px-4 py-2.5" />
                            <td className="px-4 py-2.5 text-right tabular-nums">{s.order_count}</td>
                            <td className="px-4 py-2.5 text-right tabular-nums">
                              {s.revenue_cents > 0 ? money(s.revenue_cents) : '—'}
                            </td>
                            <td className="px-4 py-2.5">{fmtDate(s.created_at)}</td>
                          </tr>
                        )
                      })}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
