import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Loader2, Users, Shield, AlertTriangle, Scale, FileText, Activity, Zap } from 'lucide-react'
import { api } from '../../../api/client'
import { useToast } from '../../../components/ui/Toast'
import type { Overview, Registration, Tab } from './types'
import { relTime } from './shared'
import { EmployeeSyncPanel } from './EmployeeSyncPanel'
import { TokensTab } from './TokensTab'
import { LifecycleActions } from './LifecycleActions'

type Tier = 'free' | 'lite' | 'x' | 'platform' | 'personal'

function tierFromRegistration(r: Registration): Tier {
  if (r.is_personal) return 'personal'
  if (r.signup_source === 'resources_free') return 'free'
  if (r.signup_source === 'matcha_lite') return 'lite'
  if (r.signup_source === 'matcha_x') return 'x'
  return 'platform'
}

const TIER_LABEL: Record<Tier, string> = { free: 'Free', lite: 'Lite', x: 'Matcha-X', platform: 'Platform', personal: 'Personal' }
const TIER_BADGE: Record<Tier, string> = {
  free: 'border-zinc-600 bg-zinc-700/30 text-zinc-300',
  lite: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  x: 'border-teal-500/40 bg-teal-500/10 text-teal-300',
  platform: 'border-violet-500/40 bg-violet-500/10 text-violet-300',
  personal: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
}

function fmtUsd(cents: number) {
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

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

export default function AdminCompanyDetail() {
  const { companyId } = useParams<{ companyId: string }>()
  const [data, setData] = useState<Overview | null>(null)
  const [registration, setRegistration] = useState<Registration | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>('employees')
  const [runningAssessment, setRunningAssessment] = useState(false)
  const { toast } = useToast()

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

  async function handleToggleIsTest() {
    if (!companyId || !registration) return
    const next = !registration.is_test
    if (next && !window.confirm(
      'Mark this company as a test/demo tenant?\n\n' +
      '- Its data will be automatically synced dev <-> prod on every deploy (sync-test-tenants.sh).\n' +
      '- It will be EXEMPTED from PII anonymization when dev is refreshed from prod (anonymize_dev.sql) — only do this for real demo data, never a live customer.'
    )) return
    try {
      await api.patch(`/admin/companies/${companyId}`, { is_test: next })
      setRegistration({ ...registration, is_test: next })
      toast(next ? 'Marked as test tenant — syncs dev <-> prod on every deploy' : 'Unmarked test tenant')
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to update test-tenant flag', 'error')
    }
  }

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
            {registration && (
              <button
                type="button"
                onClick={handleToggleIsTest}
                className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border transition-colors ${
                  registration.is_test
                    ? 'bg-amber-900/30 text-amber-400 border-amber-800/40'
                    : 'bg-zinc-900/40 text-zinc-600 border-zinc-800 hover:text-zinc-400'
                }`}
                title={
                  registration.is_test
                    ? 'Test/demo tenant — synced automatically between dev and prod on every deploy. Click to unmark.'
                    : 'Click to mark as a test/demo tenant (auto-synced dev <-> prod on every deploy).'
                }
              >
                {registration.is_test ? 'Test' : 'Mark as test'}
              </button>
            )}
            {registration?.is_suspended && (
              <span
                className="text-[10px] font-bold uppercase px-2 py-0.5 rounded border bg-red-900/30 text-red-400 border-red-800/40"
                title="Owner is suspended"
              >
                Owner suspended
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
          {companyId && <EmployeeSyncPanel companyId={companyId} />}
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
