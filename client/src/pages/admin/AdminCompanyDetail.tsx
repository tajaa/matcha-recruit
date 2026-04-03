import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Loader2, Users, Shield, AlertTriangle, Scale, FileText, Activity } from 'lucide-react'
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

type Tab = 'employees' | 'risk' | 'compliance' | 'actions'

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
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>('employees')
  const [runningAssessment, setRunningAssessment] = useState(false)

  useEffect(() => {
    if (!companyId) return
    setLoading(true)
    api.get<Overview>(`/admin/companies/${companyId}/overview`)
      .then(setData)
      .catch(() => setData(null))
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
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-zinc-100">{co.name}</h1>
            <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${co.status === 'approved' ? 'bg-emerald-900/30 text-emerald-400 border-emerald-800/40' : 'bg-amber-900/30 text-amber-400 border-amber-800/40'}`}>
              {co.status}
            </span>
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
        {([['employees', 'Employees'], ['risk', 'Risk & Incidents'], ['compliance', 'Compliance'], ['actions', 'Actions']] as [Tab, string][]).map(([t, label]) => (
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
      {tab === 'actions' && (
        <div className="space-y-6 max-w-lg">
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
