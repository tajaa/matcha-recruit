import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Loader2, Users, Shield, AlertTriangle, Scale, FileText, Activity, Zap } from 'lucide-react'
import { api } from '../../api/client'

type Overview = {
  company: {
    id: string; name: string; industry: string | null; healthcare_specialties: string[]
    size: string | null; status: string; headquarters_state: string | null
    created_at: string | null; enabled_features: Record<string, boolean>; active_employee_count: number
  }
  employees: { id: string; email: string; name: string; department: string | null; job_title: string | null; employment_type: string | null; work_state: string | null; start_date: string | null; active: boolean }[]
  risk: { overall_score: number; overall_band: string; computed_at: string | null } | null
  ir_summary: { total_open: number; critical: number; high: number; medium: number; low: number; recent_30_days: number }
  er_summary: { total_open: number; open: number; in_review: number; pending_determination: number }
  compliance: { total_locations: number; total_requirements: number; critical_alerts: number; warning_alerts: number }
  policies: { total_active: number; stale_count: number }
  recent_incidents: { id: string; incident_number: string; title: string; severity: string; status: string; created_at: string | null }[]
  recent_er_cases: { id: string; case_number: string; title: string; status: string; category: string | null; created_at: string | null }[]
}

type Registration = {
  id: string
  owner_user_id: string | null
  signup_source: string | null
  is_personal: boolean
  is_suspended: boolean
  deleted_at: string | null
  subscription: {
    pack_id: string
    status: string
    amount_cents: number
    stripe_subscription_id: string
    stripe_customer_id: string
    current_period_end: string | null
    canceled_at: string | null
  } | null
}

type Tier = 'free' | 'lite' | 'platform' | 'personal'

function tierFromRegistration(r: Registration): Tier {
  if (r.is_personal) return 'personal'
  if (r.signup_source === 'resources_free') return 'free'
  if (r.signup_source === 'matcha_lite') return 'lite'
  return 'platform'
}

const TIER_LABEL: Record<Tier, string> = { free: 'Free', lite: 'Lite', platform: 'Platform', personal: 'Personal' }
const TIER_BADGE: Record<Tier, string> = {
  free: 'border-zinc-600 bg-zinc-700/30 text-zinc-300',
  lite: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  platform: 'border-violet-500/40 bg-violet-500/10 text-violet-300',
  personal: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
}

function fmtUsd(cents: number) {
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

type Tab = 'employees' | 'risk' | 'compliance' | 'tokens' | 'actions'

const BAND_COLORS: Record<string, string> = {
  low: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  moderate: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  high: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
  critical: 'bg-red-500/10 text-red-400 border-red-500/20',
}

const SEV_DOT: Record<string, string> = {
  critical: 'bg-red-500', high: 'bg-orange-500', medium: 'bg-amber-500', low: 'bg-blue-400',
}

function StatCard({ label, value, sub, icon: Icon, color }: { label: string; value: number | string; sub?: string; icon: React.ElementType; color?: string }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon className={`w-4 h-4 ${color ?? 'text-zinc-500'}`} />
        <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">{label}</span>
      </div>
      <div className="text-2xl font-semibold text-zinc-100">{value}</div>
      {sub && <div className="text-[11px] text-zinc-500 mt-0.5">{sub}</div>}
    </div>
  )
}

function relTime(iso: string | null): string {
  if (!iso) return '—'
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (d === 0) return 'Today'
  if (d === 1) return 'Yesterday'
  return `${d}d ago`
}

export default function AdminCompanyDetail() {
  const { companyId } = useParams<{ companyId: string }>()
  const [data, setData] = useState<Overview | null>(null)
  const [registration, setRegistration] = useState<Registration | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>('employees')
  const [runningAssessment, setRunningAssessment] = useState(false)

  useEffect(() => {
    if (!companyId) return
    setLoading(true)
    Promise.all([
      api.get<Overview>(`/admin/companies/${companyId}/overview`).catch(() => null),
      api.get<Registration>(`/admin/business-registrations/${companyId}`).catch(() => null),
    ])
      .then(([overview, reg]) => {
        setData(overview)
        setRegistration(reg)
      })
      .finally(() => setLoading(false))
  }, [companyId])

  async function handleRunAssessment() {
    if (!companyId) return
    setRunningAssessment(true)
    try {
      await api.post(`/risk-assessment/admin/run/${companyId}`)
      const fresh = await api.get<Overview>(`/admin/companies/${companyId}/overview`)
      setData(fresh)
    } catch {}
    setRunningAssessment(false)
  }

  if (loading) return <div className="flex items-center justify-center min-h-[60vh]"><Loader2 className="w-5 h-5 text-zinc-500 animate-spin" /></div>
  if (!data) return <div className="p-8 text-center text-sm text-zinc-500">Company not found</div>

  const { company: co, employees, risk, ir_summary: ir, er_summary: er, compliance: comp, policies, recent_incidents, recent_er_cases } = data

  return (
    <div>
      {/* Header */}
      <div className="flex items-start gap-4 mb-6">
        <Link to="/admin/companies" className="mt-1 text-zinc-500 hover:text-zinc-300 transition-colors">
          <ArrowLeft size={18} />
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-semibold text-zinc-100">{co.name}</h1>
            {registration && (
              <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${TIER_BADGE[tierFromRegistration(registration)]}`}>
                {TIER_LABEL[tierFromRegistration(registration)]}
              </span>
            )}
            <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${co.status === 'approved' ? 'bg-emerald-900/30 text-emerald-400 border-emerald-800/40' : 'bg-amber-900/30 text-amber-400 border-amber-800/40'}`}>
              {co.status}
            </span>
            {registration?.is_suspended && (
              <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded border bg-red-900/30 text-red-400 border-red-800/40">
                Suspended
              </span>
            )}
            {registration?.deleted_at && (
              <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded border bg-zinc-900/40 text-zinc-400 border-zinc-700">
                Deleted
              </span>
            )}
            {risk && (
              <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${BAND_COLORS[risk.overall_band] ?? BAND_COLORS.moderate}`}>
                Risk: {risk.overall_score} ({risk.overall_band})
              </span>
            )}
          </div>
          <p className="text-xs text-zinc-500 mt-1">
            {co.industry ?? 'Unknown industry'}
            {co.healthcare_specialties.length > 0 && ` · ${co.healthcare_specialties.join(', ')}`}
            {co.headquarters_state && ` · ${co.headquarters_state}`}
          </p>
        </div>
        <button
          onClick={handleRunAssessment}
          disabled={runningAssessment}
          className="text-xs px-3 py-1.5 rounded-lg bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:opacity-50 transition-colors"
        >
          {runningAssessment ? 'Running...' : 'Run Assessment'}
        </button>
      </div>

      {/* Billing panel */}
      {registration && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 mb-6">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-4 h-4 text-amber-400" />
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Billing</span>
          </div>
          {registration.subscription ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
              <div>
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Pack</div>
                <div className="text-zinc-200 font-medium">{registration.subscription.pack_id}</div>
              </div>
              <div>
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Status</div>
                <div className={`font-medium ${registration.subscription.status === 'active' ? 'text-emerald-300' : 'text-zinc-400'}`}>
                  {registration.subscription.status}
                </div>
              </div>
              <div>
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Amount</div>
                <div className="text-zinc-200 font-medium">{fmtUsd(registration.subscription.amount_cents)}</div>
              </div>
              <div>
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Renews</div>
                <div className="text-zinc-200 font-medium">
                  {registration.subscription.current_period_end
                    ? new Date(registration.subscription.current_period_end).toLocaleDateString()
                    : '—'}
                </div>
              </div>
              <div className="col-span-2 md:col-span-4 flex items-center gap-3 pt-2 border-t border-zinc-800">
                <a
                  href={`https://dashboard.stripe.com/customers/${registration.subscription.stripe_customer_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] text-emerald-400 hover:text-emerald-300"
                >
                  Customer →
                </a>
                <a
                  href={`https://dashboard.stripe.com/subscriptions/${registration.subscription.stripe_subscription_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] text-emerald-400 hover:text-emerald-300"
                >
                  Subscription →
                </a>
                <span className="text-[10px] text-zinc-600 font-mono ml-auto">
                  {registration.subscription.stripe_subscription_id}
                </span>
              </div>
            </div>
          ) : (
            <div className="text-xs text-zinc-500">No active subscription on file.</div>
          )}
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        <StatCard label="Employees" value={co.active_employee_count} icon={Users} color="text-blue-400" />
        <StatCard label="Risk Score" value={risk ? risk.overall_score : '—'} sub={risk?.overall_band ?? 'No assessment'} icon={Activity} color={risk?.overall_band === 'critical' ? 'text-red-400' : risk?.overall_band === 'high' ? 'text-orange-400' : 'text-emerald-400'} />
        <StatCard label="Open Incidents" value={ir.total_open} sub={ir.critical > 0 ? `${ir.critical} critical` : `${ir.recent_30_days} last 30d`} icon={AlertTriangle} color={ir.critical > 0 ? 'text-red-400' : 'text-amber-400'} />
        <StatCard label="Open ER Cases" value={er.total_open} sub={[er.open && `${er.open} open`, er.in_review && `${er.in_review} review`, er.pending_determination && `${er.pending_determination} pending`].filter(Boolean).join(', ') || 'None'} icon={Scale} color="text-blue-400" />
        <StatCard label="Compliance" value={comp.total_requirements} sub={`${comp.total_locations} locations · ${comp.critical_alerts} critical`} icon={Shield} color={comp.critical_alerts > 0 ? 'text-red-400' : 'text-emerald-400'} />
        <StatCard label="Policies" value={policies.total_active} sub={policies.stale_count > 0 ? `${policies.stale_count} stale` : 'All current'} icon={FileText} color="text-violet-400" />
      </div>

      {/* Tabs */}
      <div className="flex gap-0 border border-zinc-700 rounded-xl overflow-hidden w-fit mb-6">
        {([['employees', 'Employees'], ['risk', 'Risk & Incidents'], ['compliance', 'Compliance'], ['tokens', 'Tokens'], ['actions', 'Actions']] as [Tab, string][]).map(([t, label]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-5 py-2 text-[11px] uppercase tracking-widest font-bold transition-colors ${tab === t ? 'bg-zinc-800 text-zinc-50' : 'bg-zinc-900 text-zinc-500 hover:text-zinc-300'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Employees tab */}
      {tab === 'employees' && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left py-2 font-medium">Name</th>
                <th className="text-left py-2 font-medium">Email</th>
                <th className="text-left py-2 font-medium">Department</th>
                <th className="text-left py-2 font-medium">Job Title</th>
                <th className="text-left py-2 font-medium">State</th>
                <th className="text-left py-2 font-medium">Type</th>
                <th className="text-left py-2 font-medium">Start</th>
                <th className="text-left py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {employees.map((e) => (
                <tr key={e.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                  <td className="py-2 text-zinc-200 font-medium">{e.name}</td>
                  <td className="py-2 text-zinc-400">{e.email}</td>
                  <td className="py-2 text-zinc-400">{e.department ?? '—'}</td>
                  <td className="py-2 text-zinc-400">{e.job_title ?? '—'}</td>
                  <td className="py-2 text-zinc-400">{e.work_state ?? '—'}</td>
                  <td className="py-2 text-zinc-400">{e.employment_type ?? '—'}</td>
                  <td className="py-2 text-zinc-400">{e.start_date ? new Date(e.start_date).toLocaleDateString() : '—'}</td>
                  <td className="py-2">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${e.active ? 'bg-emerald-900/30 text-emerald-400' : 'bg-zinc-800 text-zinc-500'}`}>
                      {e.active ? 'Active' : 'Terminated'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {employees.length === 0 && <p className="text-center text-sm text-zinc-500 py-8">No employees</p>}
        </div>
      )}

      {/* Risk & Incidents tab */}
      {tab === 'risk' && (
        <div className="space-y-6">
          {/* Risk overview */}
          {risk && (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
              <div className="flex items-center gap-4 mb-3">
                <div className="text-4xl font-bold text-zinc-100">{risk.overall_score}</div>
                <div>
                  <span className={`text-xs font-bold uppercase px-2 py-0.5 rounded border ${BAND_COLORS[risk.overall_band] ?? ''}`}>{risk.overall_band}</span>
                  <p className="text-[10px] text-zinc-500 mt-1">Computed {relTime(risk.computed_at)}</p>
                </div>
              </div>
            </div>
          )}

          {/* Incidents table */}
          <div>
            <h3 className="text-sm font-medium text-zinc-300 mb-3">Recent Incidents</h3>
            {recent_incidents.length === 0 ? (
              <p className="text-xs text-zinc-500">No incidents recorded</p>
            ) : (
              <table className="w-full text-xs">
                <thead><tr className="text-zinc-500 border-b border-zinc-800">
                  <th className="text-left py-2 font-medium">ID</th>
                  <th className="text-left py-2 font-medium">Title</th>
                  <th className="text-left py-2 font-medium">Severity</th>
                  <th className="text-left py-2 font-medium">Status</th>
                  <th className="text-left py-2 font-medium">Date</th>
                </tr></thead>
                <tbody>
                  {recent_incidents.map((inc) => (
                    <tr key={inc.id} className="border-b border-zinc-800/50">
                      <td className="py-2 text-zinc-400 font-mono">{inc.incident_number}</td>
                      <td className="py-2 text-zinc-200">{inc.title}</td>
                      <td className="py-2"><span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${SEV_DOT[inc.severity] ?? 'bg-zinc-500'}`} />{inc.severity}</td>
                      <td className="py-2 text-zinc-400">{inc.status}</td>
                      <td className="py-2 text-zinc-500">{relTime(inc.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* ER Cases table */}
          <div>
            <h3 className="text-sm font-medium text-zinc-300 mb-3">ER Cases</h3>
            {recent_er_cases.length === 0 ? (
              <p className="text-xs text-zinc-500">No ER cases</p>
            ) : (
              <table className="w-full text-xs">
                <thead><tr className="text-zinc-500 border-b border-zinc-800">
                  <th className="text-left py-2 font-medium">Case #</th>
                  <th className="text-left py-2 font-medium">Title</th>
                  <th className="text-left py-2 font-medium">Category</th>
                  <th className="text-left py-2 font-medium">Status</th>
                  <th className="text-left py-2 font-medium">Date</th>
                </tr></thead>
                <tbody>
                  {recent_er_cases.map((c) => (
                    <tr key={c.id} className="border-b border-zinc-800/50">
                      <td className="py-2 text-zinc-400 font-mono">{c.case_number}</td>
                      <td className="py-2 text-zinc-200">{c.title}</td>
                      <td className="py-2 text-zinc-400">{c.category ?? '—'}</td>
                      <td className="py-2 text-zinc-400">{c.status}</td>
                      <td className="py-2 text-zinc-500">{relTime(c.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* Compliance tab */}
      {tab === 'compliance' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="text-[10px] text-zinc-500 uppercase">Locations</div>
              <div className="text-xl font-semibold text-zinc-100 mt-1">{comp.total_locations}</div>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="text-[10px] text-zinc-500 uppercase">Requirements</div>
              <div className="text-xl font-semibold text-zinc-100 mt-1">{comp.total_requirements}</div>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="text-[10px] text-zinc-500 uppercase">Critical Alerts</div>
              <div className={`text-xl font-semibold mt-1 ${comp.critical_alerts > 0 ? 'text-red-400' : 'text-zinc-100'}`}>{comp.critical_alerts}</div>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="text-[10px] text-zinc-500 uppercase">Warnings</div>
              <div className={`text-xl font-semibold mt-1 ${comp.warning_alerts > 0 ? 'text-amber-400' : 'text-zinc-100'}`}>{comp.warning_alerts}</div>
            </div>
          </div>
          <p className="text-xs text-zinc-500">
            {policies.total_active} active policies{policies.stale_count > 0 ? ` (${policies.stale_count} stale)` : ''}
          </p>
        </div>
      )}

      {/* Actions tab */}
      {tab === 'tokens' && companyId && <TokensTab companyId={companyId} />}

      {tab === 'actions' && companyId && (
        <div className="space-y-6 max-w-2xl">
          {registration && (
            <LifecycleActions
              companyId={companyId}
              registration={registration}
              onRefresh={async () => {
                const reg = await api.get<Registration>(`/admin/business-registrations/${companyId}`).catch(() => null)
                setRegistration(reg)
              }}
            />
          )}

          <div>
            <h3 className="text-sm font-medium text-zinc-300 mb-2">Risk Assessment</h3>
            <button
              onClick={handleRunAssessment}
              disabled={runningAssessment}
              className="text-xs px-4 py-2 rounded-lg bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:opacity-50 transition-colors"
            >
              {runningAssessment ? 'Running...' : 'Run Assessment Now'}
            </button>
            {risk && <p className="text-[10px] text-zinc-500 mt-2">Last run: {relTime(risk.computed_at)}</p>}
          </div>

          <div>
            <h3 className="text-sm font-medium text-zinc-300 mb-2">Enabled Features</h3>
            <div className="flex flex-wrap gap-2">
              {Object.entries(co.enabled_features).filter(([, v]) => v).map(([k]) => (
                <span key={k} className="text-[10px] px-2 py-1 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                  {k.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}


// ── Tokens Tab ───────────────────────────────────────────────────────────────

type TokenBudget = {
  free_tokens_used: number; free_token_limit: number; free_tokens_remaining: number
  subscription_tokens_used: number; subscription_token_limit: number; subscription_tokens_remaining: number
  total_tokens_remaining: number; has_active_subscription: boolean
}
type UsageEvent = {
  id: string; model: string | null; total_tokens: number | null; operation: string | null; created_at: string
}
type TokenDetail = { budget: TokenBudget; recent_usage: UsageEvent[] }

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(n)
}

function TokensTab({ companyId }: { companyId: string }) {
  const [detail, setDetail] = useState<TokenDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [grantAmount, setGrantAmount] = useState('')
  const [grantDesc, setGrantDesc] = useState('')
  const [granting, setGranting] = useState(false)

  function load() {
    api.get<TokenDetail>(`/matcha-work/admin/companies/${companyId}/token-usage`)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [companyId])

  async function handleGrant() {
    const tokens = parseInt(grantAmount)
    if (!tokens || tokens <= 0) return
    setGranting(true)
    try {
      await api.post(`/matcha-work/admin/companies/${companyId}/tokens`, {
        tokens,
        description: grantDesc || undefined,
      })
      setGrantAmount('')
      setGrantDesc('')
      load()
    } catch {}
    setGranting(false)
  }

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="w-4 h-4 text-zinc-500 animate-spin" /></div>
  if (!detail) return <p className="text-sm text-zinc-500">Failed to load token data</p>

  const b = detail.budget

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-emerald-400" />
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Free Tokens</span>
          </div>
          <div className="text-xl font-semibold text-zinc-100">{fmtTokens(b.free_tokens_remaining)}</div>
          <div className="text-[11px] text-zinc-500">{fmtTokens(b.free_tokens_used)} / {fmtTokens(b.free_token_limit)} used</div>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-blue-400" />
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Subscription</span>
          </div>
          <div className="text-xl font-semibold text-zinc-100">
            {b.has_active_subscription ? fmtTokens(b.subscription_tokens_remaining) : 'None'}
          </div>
          {b.has_active_subscription && (
            <div className="text-[11px] text-zinc-500">{fmtTokens(b.subscription_tokens_used)} / {fmtTokens(b.subscription_token_limit)} used</div>
          )}
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-zinc-400" />
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Total Remaining</span>
          </div>
          <div className="text-xl font-semibold text-zinc-100">{fmtTokens(b.total_tokens_remaining)}</div>
        </div>
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
        <h3 className="text-sm font-medium text-zinc-300 mb-3">Grant Tokens</h3>
        <div className="flex items-end gap-3">
          <div>
            <label className="block text-[10px] text-zinc-500 mb-1">Amount</label>
            <input
              type="number"
              value={grantAmount}
              onChange={(e) => setGrantAmount(e.target.value)}
              placeholder="e.g. 500000"
              className="w-36 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
            />
          </div>
          <div className="flex-1">
            <label className="block text-[10px] text-zinc-500 mb-1">Description (optional)</label>
            <input
              type="text"
              value={grantDesc}
              onChange={(e) => setGrantDesc(e.target.value)}
              placeholder="Reason for grant"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
            />
          </div>
          <button
            onClick={handleGrant}
            disabled={granting || !grantAmount}
            className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-500 disabled:opacity-40 transition-colors"
          >
            {granting ? 'Granting...' : 'Grant'}
          </button>
        </div>
      </div>

      <div>
        <h3 className="text-sm font-medium text-zinc-300 mb-3">Recent Usage</h3>
        {detail.recent_usage.length === 0 ? (
          <p className="text-sm text-zinc-500">No usage yet</p>
        ) : (
          <div className="overflow-hidden rounded-xl border border-zinc-800">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-zinc-900 text-zinc-500 uppercase tracking-widest text-[10px]">
                  <th className="text-left px-4 py-2.5 font-medium">Date</th>
                  <th className="text-left px-4 py-2.5 font-medium">Model</th>
                  <th className="text-right px-4 py-2.5 font-medium">Tokens</th>
                  <th className="text-left px-4 py-2.5 font-medium">Operation</th>
                </tr>
              </thead>
              <tbody>
                {detail.recent_usage.map((e) => (
                  <tr key={e.id} className="border-t border-zinc-800/50">
                    <td className="px-4 py-2 text-zinc-400">{relTime(e.created_at)}</td>
                    <td className="px-4 py-2 text-zinc-300">{e.model ?? '—'}</td>
                    <td className="px-4 py-2 text-right text-zinc-300">{e.total_tokens?.toLocaleString() ?? '—'}</td>
                    <td className="px-4 py-2 text-zinc-400">{e.operation ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}


// ── Lifecycle Actions (Account / Billing / Tier) ─────────────────────────────

type Charge = {
  id: string
  amount: number
  amount_refunded: number
  currency: string
  created: number
  status: string
  description: string | null
}

const TIER_OPTIONS = [
  { value: 'resources_free', label: 'Free (Resources only)' },
  { value: 'matcha_lite', label: 'Matcha Lite' },
  { value: 'bespoke', label: 'Platform / Bespoke (full features)' },
  { value: 'ir_only_self_serve', label: 'IR Cap (incidents + employees + discipline)' },
]

function LifecycleActions({
  companyId,
  registration,
  onRefresh,
}: {
  companyId: string
  registration: Registration
  onRefresh: () => Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const [resetUrl, setResetUrl] = useState<string | null>(null)
  const [refundOpen, setRefundOpen] = useState(false)
  const [tierTarget, setTierTarget] = useState('')

  async function withBusy(fn: () => Promise<void>) {
    if (busy) return
    setBusy(true)
    try { await fn() } finally { setBusy(false) }
  }

  async function suspendOrUnsuspend() {
    if (!registration.owner_user_id) return
    await withBusy(async () => {
      const path = registration.is_suspended ? 'unsuspend' : 'suspend'
      await api.post(`/admin/users/${registration.owner_user_id}/${path}`, {})
      await onRefresh()
    })
  }

  async function passwordReset() {
    if (!registration.owner_user_id) return
    await withBusy(async () => {
      const res = await api.post<{ reset_url: string }>(`/admin/users/${registration.owner_user_id}/password-reset`, {})
      setResetUrl(res.reset_url)
    })
  }

  async function cancelSub(immediate: boolean) {
    await withBusy(async () => {
      const qs = immediate ? '?immediate=true' : ''
      await api.post(`/admin/companies/${companyId}/cancel-subscription${qs}`, {})
      await onRefresh()
    })
  }

  async function changeTier() {
    if (!tierTarget) return
    if (!confirm(`Switch tier to "${tierTarget}"? This rewrites enabled_features.`)) return
    await withBusy(async () => {
      await api.patch(`/admin/companies/${companyId}/tier`, { tier: tierTarget })
      await onRefresh()
    })
  }

  async function softDelete() {
    if (!confirm('Soft-delete this company? It disappears from lists; rows persist for audit.')) return
    await withBusy(async () => {
      await api.delete(`/admin/companies/${companyId}`)
      await onRefresh()
    })
  }

  async function restore() {
    await withBusy(async () => {
      await api.post(`/admin/companies/${companyId}/restore`, {})
      await onRefresh()
    })
  }

  return (
    <>
      <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
        <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 mb-3">Account</h3>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={suspendOrUnsuspend}
            disabled={busy || !registration.owner_user_id}
            className={`text-xs px-3 py-1.5 rounded-lg disabled:opacity-40 transition-colors ${
              registration.is_suspended
                ? 'bg-emerald-700 hover:bg-emerald-600 text-white'
                : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-200'
            }`}
          >
            {registration.is_suspended ? 'Unsuspend' : 'Suspend'}
          </button>
          <button
            onClick={passwordReset}
            disabled={busy || !registration.owner_user_id}
            className="text-xs px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 disabled:opacity-40"
          >
            Issue password reset
          </button>
          {!registration.deleted_at ? (
            <button
              onClick={softDelete}
              disabled={busy}
              className="text-xs px-3 py-1.5 rounded-lg bg-red-900/40 hover:bg-red-900/60 text-red-200 disabled:opacity-40"
            >
              Soft-delete
            </button>
          ) : (
            <button
              onClick={restore}
              disabled={busy}
              className="text-xs px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 disabled:opacity-40"
            >
              Restore
            </button>
          )}
        </div>
        {resetUrl && (
          <div className="mt-3 p-3 rounded-lg border border-emerald-700/40 bg-emerald-900/20">
            <div className="text-[10px] text-emerald-300 uppercase tracking-wider mb-1">Reset link (1h)</div>
            <code className="text-[11px] break-all text-emerald-100">{resetUrl}</code>
            <button
              onClick={() => { navigator.clipboard?.writeText(resetUrl); }}
              className="block mt-2 text-[11px] text-emerald-300 hover:text-emerald-200"
            >
              Copy →
            </button>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
        <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 mb-3">Billing</h3>
        {registration.subscription ? (
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => cancelSub(false)}
              disabled={busy || registration.subscription?.status !== 'active'}
              className="text-xs px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 disabled:opacity-40"
            >
              Cancel at period end
            </button>
            <button
              onClick={() => cancelSub(true)}
              disabled={busy}
              className="text-xs px-3 py-1.5 rounded-lg bg-red-900/40 hover:bg-red-900/60 text-red-200 disabled:opacity-40"
            >
              Cancel immediately
            </button>
            <button
              onClick={() => setRefundOpen(true)}
              disabled={busy}
              className="text-xs px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 disabled:opacity-40"
            >
              Issue refund…
            </button>
          </div>
        ) : (
          <p className="text-xs text-zinc-500">No subscription. Refunds and cancellations require a Stripe customer.</p>
        )}
      </section>

      <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
        <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 mb-3">Tier</h3>
        <div className="flex items-center gap-2">
          <select
            value={tierTarget}
            onChange={(e) => setTierTarget(e.target.value)}
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-zinc-500"
          >
            <option value="">Pick a tier…</option>
            {TIER_OPTIONS.filter((t) => t.value !== registration.signup_source).map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          <button
            onClick={changeTier}
            disabled={busy || !tierTarget}
            className="text-xs px-3 py-2 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-40"
          >
            Switch
          </button>
        </div>
        <p className="text-[10px] text-zinc-600 mt-2">
          Current: <span className="font-mono text-zinc-400">{registration.signup_source ?? 'bespoke'}</span>.
          Switching rewrites enabled_features to the target tier's preset.
        </p>
      </section>

      {refundOpen && (
        <RefundModal
          companyId={companyId}
          onClose={() => setRefundOpen(false)}
          onDone={() => { setRefundOpen(false); onRefresh() }}
        />
      )}
    </>
  )
}

function RefundModal({
  companyId,
  onClose,
  onDone,
}: {
  companyId: string
  onClose: () => void
  onDone: () => void
}) {
  const [charges, setCharges] = useState<Charge[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [chargeId, setChargeId] = useState<string>('')
  const [amount, setAmount] = useState<string>('')
  const [reason, setReason] = useState<string>('requested_by_customer')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api.get<{ charges: Charge[] }>(`/admin/companies/${companyId}/charges`)
      .then((r) => setCharges(r.charges))
      .catch((e) => setError(e?.message ?? 'Failed to load charges'))
  }, [companyId])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!chargeId) return
    setSubmitting(true)
    setError(null)
    try {
      const body: { charge_id: string; amount_cents?: number; reason?: string } = { charge_id: chargeId }
      if (amount.trim()) body.amount_cents = parseInt(amount, 10)
      if (reason) body.reason = reason
      await api.post(`/admin/companies/${companyId}/refund`, body)
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Refund failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <form onSubmit={submit} className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 w-full max-w-lg">
        <h3 className="text-sm font-semibold text-zinc-100 mb-1">Issue refund</h3>
        <p className="text-xs text-zinc-500 mb-4">Pick a charge. Leave amount blank for a full refund.</p>
        <div className="space-y-3">
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Charge</label>
            {charges === null ? (
              <p className="text-xs text-zinc-500">Loading charges…</p>
            ) : charges.length === 0 ? (
              <p className="text-xs text-zinc-500">No charges on this customer yet.</p>
            ) : (
              <select
                value={chargeId}
                onChange={(e) => setChargeId(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-zinc-500"
              >
                <option value="">Pick a charge…</option>
                {charges.map((c) => (
                  <option key={c.id} value={c.id}>
                    ${(c.amount / 100).toFixed(2)} {c.currency.toUpperCase()} ·{' '}
                    {new Date(c.created * 1000).toLocaleDateString()} · {c.status}
                    {c.amount_refunded > 0 && ` (${(c.amount_refunded / 100).toFixed(2)} refunded)`}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Amount (cents) — optional</label>
              <input
                value={amount}
                onChange={(e) => setAmount(e.target.value.replace(/\D/g, ''))}
                placeholder="full refund if blank"
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-zinc-500"
              />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Reason</label>
              <select
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-zinc-500"
              >
                <option value="requested_by_customer">requested_by_customer</option>
                <option value="duplicate">duplicate</option>
                <option value="fraudulent">fraudulent</option>
              </select>
            </div>
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button type="button" onClick={onClose} className="text-xs px-3 py-1.5 rounded-lg text-zinc-400 hover:text-zinc-200">
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || !chargeId}
            className="text-xs px-3 py-1.5 rounded-lg bg-red-900/50 hover:bg-red-900/70 text-red-200 disabled:opacity-40"
          >
            {submitting ? 'Refunding…' : 'Refund'}
          </button>
        </div>
      </form>
    </div>
  )
}
