import { useState, useEffect, type FormEvent, type ReactNode } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft, MapPin, FileText, Shield, AlertTriangle,
  Clock, Building2, Users, Loader2, AlertCircle,
  TrendingUp, TrendingDown, Minus, Plus, Trash2, Gauge, HeartPulse, Boxes, Sparkles, FileDown, Download,
} from 'lucide-react'
import { Card } from '../../components/ui'
import { StatCard } from '../../components/dashboard'
import {
  fetchBrokerClientDetail, fetchWcClientDetail, recordWcMod, deleteWcMod,
  fetchEplClientDetail, recordEplAttestation,
  downloadTenantSubmission, fetchTenantCoverageGap,
  fetchWcClassCodes, fetchWcClassExposures, recordWcClassExposure, deleteWcClassExposure,
  autoMapClassExposures, type ClassAutoMap,
  fetchClientControls, downloadClientControls,
  fetchClientDefenseIncidents, downloadDefenseIncident,
  fetchClientDefenseErCases, downloadDefenseErCase,
  type DefenseIncident, type DefenseErCase,
} from '../../api/broker'
import { SubmissionPanel } from '../../components/broker/SubmissionPanel'
import type {
  BrokerClientDetailResponse, WcClientDetailResponse,
  EplReadiness, EplFactor, EplAttestationStatus,
  WcClassCode, WcClassExposure,
} from '../../types/broker'
import type { ControlsRegister } from '../../types/controlsEvidence'

const riskColors: Record<string, string> = {
  healthy: 'bg-zinc-500',
  watch: 'bg-zinc-700',
  at_risk: 'bg-zinc-800',
}

const riskLabels: Record<string, string> = {
  healthy: 'Healthy',
  watch: 'Watch',
  at_risk: 'At Risk',
}

const severityColors: Record<string, string> = {
  critical: 'bg-zinc-100 text-zinc-900',
  high: 'bg-zinc-300 text-zinc-900',
  medium: 'bg-zinc-500 text-zinc-100',
  low: 'bg-zinc-800 text-zinc-400',
}

type Tab = 'overview' | 'compliance' | 'policies' | 'ir_er' | 'wc' | 'epl' | 'controls' | 'defense' | 'submission' | 'activity'

const tabs: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'compliance', label: 'Compliance' },
  { key: 'policies', label: 'Policies & Handbooks' },
  { key: 'ir_er', label: 'IR / ER' },
  { key: 'wc', label: "Workers' Comp" },
  { key: 'epl', label: 'EPL Readiness' },
  { key: 'controls', label: 'Controls' },
  { key: 'defense', label: 'Defense Files' },
  { key: 'submission', label: 'Submission' },
  { key: 'activity', label: 'Activity' },
]

function complianceColor(rate: number) {
  if (rate >= 80) return 'text-zinc-100'
  if (rate >= 50) return 'text-zinc-400'
  return 'text-zinc-600'
}

function formatRelative(ts: string) {
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 30) return `${days}d ago`
  return new Date(ts).toLocaleDateString()
}

export default function BrokerClientDetail() {
  const { companyId } = useParams<{ companyId: string }>()
  const [data, setData] = useState<BrokerClientDetailResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  useEffect(() => {
    if (!companyId) return
    setLoading(true)
    fetchBrokerClientDetail(companyId)
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [companyId])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 text-zinc-500 animate-spin" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
        <AlertCircle className="h-8 w-8 mb-2" />
        <p className="text-sm">Unable to load client details. Please try again later.</p>
      </div>
    )
  }

  const { company, compliance, policies, ir_summary, er_summary, handbooks, recent_activity } = data

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        to="/broker"
        className="inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Book of Business
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight">{company.name}</h1>
          <p className="text-sm text-zinc-500 mt-1">
            {[company.industry, company.size, company.link_status].filter(Boolean).join(' \u00b7 ')}
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 text-xs text-zinc-300 px-2.5 py-1 rounded-full bg-zinc-800 border border-zinc-700">
          <span className={`h-2 w-2 rounded-full ${riskColors[company.risk_signal] ?? 'bg-zinc-600'}`} />
          {riskLabels[company.risk_signal] ?? company.risk_signal}
        </span>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Employees" value={company.active_employee_count} icon={Users} />
        <StatCard label="Compliance" value={`${Math.round(company.policy_compliance_rate)}%`} icon={Shield} />
        <StatCard
          label="Open Actions"
          value={company.open_action_items}
          icon={AlertTriangle}
          urgent={company.open_action_items > 0}
        />
        <StatCard label="Active Policies" value={policies.total_active} icon={FileText} />
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-zinc-800">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === t.key
                ? 'text-zinc-100 border-b-2 border-zinc-100'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'overview' && (
        <OverviewTab
          compliance={compliance}
          policies={policies}
          ir={ir_summary}
          er={er_summary}
          onboardingStage={company.onboarding_stage}
        />
      )}
      {activeTab === 'compliance' && <ComplianceTab compliance={compliance} />}
      {activeTab === 'policies' && <PoliciesTab policies={policies} handbooks={handbooks} />}
      {activeTab === 'ir_er' && <IRERTab ir={ir_summary} er={er_summary} />}
      {activeTab === 'wc' && companyId && <WcTab companyId={companyId} />}
      {activeTab === 'epl' && companyId && <EplTab companyId={companyId} />}
      {activeTab === 'controls' && companyId && <ControlsTab companyId={companyId} />}
      {activeTab === 'defense' && companyId && <DefenseTab companyId={companyId} />}
      {activeTab === 'submission' && companyId && (
        <SubmissionPanel
          onDownload={() => downloadTenantSubmission(companyId)}
          onAnalyze={() => fetchTenantCoverageGap(companyId)}
        />
      )}
      {activeTab === 'activity' && <ActivityTab activity={recent_activity} />}
    </div>
  )
}

/* ──────────────────── Overview Tab ──────────────────── */

function OverviewTab({
  compliance,
  policies,
  ir,
  er,
  onboardingStage,
}: {
  compliance: BrokerClientDetailResponse['compliance']
  policies: BrokerClientDetailResponse['policies']
  ir: BrokerClientDetailResponse['ir_summary']
  er: BrokerClientDetailResponse['er_summary']
  onboardingStage: string | null
}) {
  return (
    <div className="space-y-4">
      {onboardingStage && (
        <Card className="p-4">
          <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">Onboarding Stage</h3>
          <p className="text-sm text-zinc-200 capitalize">{onboardingStage.replace(/_/g, ' ')}</p>
        </Card>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <MapPin className="h-4 w-4 text-zinc-500" />
            <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Compliance Locations</h3>
          </div>
          <p className="text-xl font-semibold text-zinc-100">{compliance.total_locations}</p>
          <p className="text-xs text-zinc-500 mt-1">{compliance.total_requirements} total requirements</p>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <FileText className="h-4 w-4 text-zinc-500" />
            <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Policy Compliance</h3>
          </div>
          <p className={`text-xl font-semibold ${complianceColor(policies.compliance_rate)}`}>
            {Math.round(policies.compliance_rate)}%
          </p>
          <p className="text-xs text-zinc-500 mt-1">{policies.total_active} active policies</p>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="h-4 w-4 text-zinc-500" />
            <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Open Incidents</h3>
          </div>
          <p className="text-xl font-semibold text-zinc-100">{ir.total_open}</p>
          <p className="text-xs text-zinc-500 mt-1">{ir.recent_30_days} in last 30 days</p>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <Building2 className="h-4 w-4 text-zinc-500" />
            <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider">ER Cases</h3>
          </div>
          <p className="text-xl font-semibold text-zinc-100">{er.total_open}</p>
          <p className="text-xs text-zinc-500 mt-1">open cases</p>
        </Card>
      </div>
    </div>
  )
}

/* ──────────────────── Compliance Tab ──────────────────── */

function ComplianceTab({ compliance }: { compliance: BrokerClientDetailResponse['compliance'] }) {
  if (compliance.locations.length === 0) {
    return (
      <Card className="p-5">
        <p className="text-sm text-zinc-500">No compliance locations configured.</p>
      </Card>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {compliance.locations.map((loc) => (
        <Card key={loc.id} className="p-4">
          <div className="flex items-start justify-between mb-3">
            <div>
              <h3 className="text-sm font-medium text-zinc-200">
                {loc.name ?? `${loc.city}, ${loc.state}`}
              </h3>
              {loc.name && (
                <p className="text-xs text-zinc-500 mt-0.5">{loc.city}, {loc.state}</p>
              )}
            </div>
            <span className="text-xs text-zinc-400">
              {loc.total_requirements} req.
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(loc.categories).map(([cat, count]) => (
              <span
                key={cat}
                className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full ${
                  count === 0
                    ? 'bg-zinc-800 text-zinc-500'
                    : 'bg-zinc-800 text-zinc-300'
                }`}
              >
                {cat}: <span className="">{count}</span>
              </span>
            ))}
          </div>
        </Card>
      ))}
    </div>
  )
}

/* ──────────────────── Policies & Handbooks Tab ──────────────────── */

function PoliciesTab({
  policies,
  handbooks,
}: {
  policies: BrokerClientDetailResponse['policies']
  handbooks: BrokerClientDetailResponse['handbooks']
}) {
  return (
    <div className="space-y-6">
      {/* Policy table */}
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-4">Policies</h3>
        {policies.items.length === 0 ? (
          <p className="text-sm text-zinc-500">No policies configured.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-800/60">
                  <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Title</th>
                  <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Category</th>
                  <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Signatures</th>
                  <th className="pb-2 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Rate</th>
                </tr>
              </thead>
              <tbody>
                {policies.items.map((p) => (
                  <tr key={p.id} className="border-b border-zinc-800/30 last:border-0">
                    <td className="py-2.5 pr-4 text-zinc-200 font-medium">{p.title}</td>
                    <td className="py-2.5 pr-4 text-zinc-400 text-xs">{p.category ?? '\u2014'}</td>
                    <td className="py-2.5 pr-4 text-right text-zinc-300 tabular-nums">
                      {p.signed_count}/{p.total_count}
                    </td>
                    <td className="py-2.5 text-right">
                      <span className={`tabular-nums ${complianceColor(p.signature_rate)}`}>
                        {Math.round(p.signature_rate)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Handbook coverage */}
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-4">Handbook Coverage</h3>
        {handbooks.length === 0 ? (
          <p className="text-sm text-zinc-500">No handbooks found.</p>
        ) : (
          <div className="space-y-3">
            {handbooks.map((h) => {
              const strengthColor =
                h.strength_label === 'Strong' ? 'text-zinc-100' :
                h.strength_label === 'Moderate' ? 'text-zinc-400' : 'text-zinc-600'
              return (
                <div key={h.handbook_id} className="flex items-center justify-between py-2 border-b border-zinc-800/30 last:border-0">
                  <div>
                    <p className="text-sm text-zinc-200">{h.handbook_title}</p>
                    <p className="text-xs text-zinc-500 mt-0.5">{h.total_sections} sections, {h.state_count} states</p>
                  </div>
                  <div className="text-right">
                    <p className={`text-sm font-medium ${strengthColor}`}>
                      {Math.round(h.strength_score)}%
                    </p>
                    <p className={`text-xs ${strengthColor}`}>{h.strength_label}</p>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Card>
    </div>
  )
}

/* ──────────────────── IR / ER Tab ──────────────────── */

function IRERTab({
  ir,
  er,
}: {
  ir: BrokerClientDetailResponse['ir_summary']
  er: BrokerClientDetailResponse['er_summary']
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* Incidents */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <AlertTriangle className="h-4 w-4 text-zinc-500" />
          <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Incidents</h3>
        </div>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-500">Total Open</span>
            <span className="text-sm font-medium text-zinc-200">{ir.total_open}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-500">Last 30 Days</span>
            <span className="text-sm font-medium text-zinc-200">{ir.recent_30_days}</span>
          </div>
          {Object.keys(ir.by_severity).length > 0 && (
            <div className="pt-2 border-t border-zinc-800/40">
              <p className="text-[11px] text-zinc-500 uppercase tracking-wider mb-2">By Severity</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(ir.by_severity).map(([sev, count]) => (
                  <span
                    key={sev}
                    className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full ${
                      severityColors[sev] ?? 'bg-zinc-700 text-zinc-300'
                    }`}
                  >
                    {sev}: <span className="">{count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </Card>

      {/* ER Cases */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <Building2 className="h-4 w-4 text-zinc-500" />
          <h3 className="text-sm font-medium text-zinc-200 tracking-wide">ER Cases</h3>
        </div>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-500">Total Open</span>
            <span className="text-sm font-medium text-zinc-200">{er.total_open}</span>
          </div>
          {Object.keys(er.by_status).length > 0 && (
            <div className="pt-2 border-t border-zinc-800/40">
              <p className="text-[11px] text-zinc-500 uppercase tracking-wider mb-2">By Status</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(er.by_status).map(([status, count]) => (
                  <span
                    key={status}
                    className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-300"
                  >
                    {status}: <span className="">{count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}

/* ──────────────────── Activity Tab ──────────────────── */

function ActivityTab({ activity }: { activity: BrokerClientDetailResponse['recent_activity'] }) {
  if (activity.length === 0) {
    return (
      <Card className="p-5">
        <p className="text-sm text-zinc-500">No recent activity.</p>
      </Card>
    )
  }

  const sourceBadge: Record<string, string> = {
    IR: 'bg-zinc-800 text-zinc-400',
    ER: 'bg-zinc-800 text-zinc-500',
  }

  return (
    <Card className="p-5">
      <div className="space-y-0">
        {activity.map((a, i) => (
          <div key={i} className="flex items-start gap-3 py-3 border-b border-zinc-800/30 last:border-0">
            <Clock className="h-4 w-4 text-zinc-600 mt-0.5 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-zinc-200">{a.action}</p>
              <p className="text-xs text-zinc-500 mt-0.5">{formatRelative(a.timestamp)}</p>
            </div>
            <span className={`text-[11px] px-2 py-0.5 rounded-full flex-shrink-0 ${
              sourceBadge[a.source] ?? 'bg-zinc-800 text-zinc-400'
            }`}>
              {a.source}
            </span>
          </div>
        ))}
      </div>
    </Card>
  )
}

/* ──────────────────── Workers' Comp Tab ──────────────────── */

const WC_BAND_TONE: Record<string, string> = {
  critical: 'text-red-400',
  at_risk: 'text-orange-400',
  fair: 'text-amber-400',
  good: 'text-emerald-400',
  unknown: 'text-zinc-500',
}

function pct(n: number | null | undefined, digits = 1) {
  if (n === null || n === undefined) return '—'
  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}%`
}

function rateTone(trend: string) {
  // Rate increase = premiums up = bad for the client.
  return trend === 'increase' ? 'text-red-400' : trend === 'decrease' ? 'text-emerald-400' : 'text-zinc-400'
}

function DeltaPill({ value }: { value: number | null }) {
  if (value === null || value === undefined) return <span className="text-zinc-600 text-[11px]">{'—'}</span>
  const flat = value === 0
  // Up is worse for TRIR/DART/lost-days.
  const tone = flat ? 'text-zinc-500' : value > 0 ? 'text-red-400' : 'text-emerald-400'
  const Icon = flat ? Minus : value > 0 ? TrendingUp : TrendingDown
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-mono ${tone}`}>
      <Icon className="h-3 w-3" />{Math.abs(value).toFixed(1)}%
    </span>
  )
}

function MetricCell({ label, value, sub, delta, tone }: {
  label: string; value: ReactNode; sub?: string; delta?: ReactNode; tone?: string
}) {
  return (
    <div className="bg-zinc-900 px-4 py-3">
      <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{label}</div>
      <div className={`text-xl font-light font-mono mt-1 ${tone ?? 'text-zinc-200'}`}>{value}</div>
      <div className="flex items-center gap-2 mt-0.5">
        {delta}
        {sub && <span className="text-[10px] text-zinc-600">{sub}</span>}
      </div>
    </div>
  )
}

function TaxCell({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-lg bg-zinc-900/60 py-2">
      <div className={`text-lg font-mono ${tone}`}>{value}</div>
      <div className="text-[10px] text-zinc-500 mt-0.5">{label}</div>
    </div>
  )
}

function WcTab({ companyId }: { companyId: string }) {
  const [detail, setDetail] = useState<WcClientDetailResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ policy_period_start: '', experience_mod: '', carrier: '', annual_premium: '', note: '' })
  const [saving, setSaving] = useState(false)
  const [formErr, setFormErr] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(false)
    fetchWcClientDetail(companyId)
      .then(setDetail)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }
  useEffect(load, [companyId])

  const submitMod = async (e: FormEvent) => {
    e.preventDefault()
    const mod = parseFloat(form.experience_mod)
    if (!form.policy_period_start || !mod || mod <= 0) {
      setFormErr('Enter a policy start date and a positive experience mod.')
      return
    }
    setSaving(true)
    setFormErr(null)
    try {
      await recordWcMod(companyId, {
        policy_period_start: form.policy_period_start,
        experience_mod: mod,
        carrier: form.carrier || undefined,
        annual_premium: form.annual_premium ? parseFloat(form.annual_premium) : undefined,
        note: form.note || undefined,
      })
      setForm({ policy_period_start: '', experience_mod: '', carrier: '', annual_premium: '', note: '' })
      setShowForm(false)
      load()
    } catch {
      setFormErr('Could not save. Try again.')
    } finally {
      setSaving(false)
    }
  }

  const removeMod = async (id: string) => {
    try {
      await deleteWcMod(companyId, id)
      load()
    } catch { /* leave list as-is on failure */ }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-40"><Loader2 className="h-5 w-5 text-zinc-500 animate-spin" /></div>
  }
  if (error || !detail) {
    return <Card className="p-5"><p className="text-sm text-zinc-500">Unable to load Workers&rsquo; Comp data.</p></Card>
  }

  const m = detail.metrics
  const benchRatio = m.trir && m.benchmark && m.benchmark.trir > 0 ? m.trir / m.benchmark.trir : null
  const latestMod = detail.mods.length ? detail.mods[detail.mods.length - 1] : null
  const cb = m.claim_breakdown
  const typed = cb.cumulative_trauma + cb.acute
  const totalForMix = Math.max(cb.cumulative_trauma + cb.acute + cb.unknown, 1)
  const inputCls = 'w-full bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500'

  return (
    <div className="space-y-4">
      {/* Metric header */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
        <MetricCell
          label="TRIR"
          value={m.trir ?? '—'}
          sub={benchRatio ? `${benchRatio.toFixed(1)}× bench` : (m.benchmark ? `bench ${m.benchmark.trir}` : 'no benchmark')}
          delta={<DeltaPill value={m.prior.trir_delta_pct} />}
          tone={WC_BAND_TONE[m.severity_band]}
        />
        <MetricCell label="DART" value={m.dart_rate ?? '—'} sub={m.benchmark ? `bench ${m.benchmark.dart}` : undefined} delta={<DeltaPill value={m.prior.dart_delta_pct} />} />
        <MetricCell label="Recordables" value={m.recordable_cases} sub={`${m.dart_cases} DART`} />
        <MetricCell label="Lost days" value={m.lost_days} delta={<DeltaPill value={m.prior.lost_days_delta_pct} />} />
        <MetricCell
          label="Exp. Mod"
          value={latestMod ? latestMod.experience_mod.toFixed(2) : '—'}
          sub={latestMod ? (latestMod.experience_mod > 1 ? 'debit' : latestMod.experience_mod < 1 ? 'credit' : 'unity') : 'none on file'}
          tone={latestMod ? (latestMod.experience_mod > 1 ? 'text-red-400' : latestMod.experience_mod < 1 ? 'text-emerald-400' : 'text-zinc-300') : 'text-zinc-600'}
        />
        <MetricCell label="Days since" value={m.days_since_last_recordable ?? '—'} sub="last recordable" />
      </div>

      {m.data_quality.insufficient_population && (
        <p className="text-[11px] text-amber-400/80">Low exposure base &mdash; TRIR/DART are directional only.</p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Claim taxonomy */}
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="h-4 w-4 text-zinc-500" />
            <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Claim mix</h3>
          </div>
          <div className="flex h-2 rounded-full overflow-hidden bg-zinc-800 mb-3">
            <div className="bg-red-500/70" style={{ width: `${(cb.cumulative_trauma / totalForMix) * 100}%` }} />
            <div className="bg-amber-500/70" style={{ width: `${(cb.acute / totalForMix) * 100}%` }} />
            <div className="bg-zinc-600" style={{ width: `${(cb.unknown / totalForMix) * 100}%` }} />
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <TaxCell label="Cumulative trauma" value={cb.cumulative_trauma} tone="text-red-400" />
            <TaxCell label="Acute" value={cb.acute} tone="text-amber-400" />
            <TaxCell label="Untyped" value={cb.unknown} tone="text-zinc-400" />
          </div>
          <div className="mt-4 pt-3 border-t border-zinc-800/60 flex items-center justify-between">
            <span className="text-xs text-zinc-500">Post-termination claims</span>
            <span className={`text-sm font-mono ${m.post_termination_cases > 0 ? 'text-red-400' : 'text-zinc-400'}`}>{m.post_termination_cases}</span>
          </div>
          {typed === 0 && (
            <p className="text-[11px] text-zinc-600 mt-2">Type recordables (acute vs cumulative trauma) on each incident to populate this.</p>
          )}
        </Card>

        {/* Return to work */}
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-4">
            <HeartPulse className="h-4 w-4 text-zinc-500" />
            <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Return to work</h3>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <TaxCell label="Lost-time" value={m.rtw.lost_time_cases} tone="text-zinc-300" />
            <TaxCell label="Open" value={m.rtw.open} tone={m.rtw.open > 0 ? 'text-orange-400' : 'text-zinc-400'} />
            <TaxCell label="Resolved" value={m.rtw.resolved} tone="text-emerald-400" />
          </div>
          <div className="mt-4 pt-3 border-t border-zinc-800/60 flex items-center justify-between">
            <span className="text-xs text-zinc-500">Avg days to RTW</span>
            <span className="text-sm font-mono text-zinc-300">{m.rtw.avg_days_to_rtw ?? '—'}</span>
          </div>
        </Card>
      </div>

      {/* NCCI jurisdiction overlay */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <MapPin className="h-4 w-4 text-zinc-500" />
          <h3 className="text-sm font-medium text-zinc-200 tracking-wide">NCCI rate trend by state</h3>
          <span className="text-[11px] text-zinc-600">2026 loss-cost filings</span>
        </div>
        {detail.states.length === 0 ? (
          <p className="text-sm text-zinc-500">No operating states on file (add business locations to enable the jurisdiction overlay).</p>
        ) : (
          <div className="space-y-2">
            {detail.states.map((s) => (
              <div key={s.state} className="flex items-center justify-between py-1.5 border-b border-zinc-800/30 last:border-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-zinc-200 w-8">{s.state}</span>
                  {s.rate?.note && <span className="text-[11px] text-zinc-600">{s.rate.note}</span>}
                </div>
                {s.rate ? (
                  <span className={`inline-flex items-center gap-1 text-sm font-mono ${rateTone(s.rate.trend)}`}>
                    {s.rate.trend === 'increase' ? <TrendingUp className="h-3.5 w-3.5" /> : s.rate.trend === 'decrease' ? <TrendingDown className="h-3.5 w-3.5" /> : <Minus className="h-3.5 w-3.5" />}
                    {pct(s.rate.loss_cost_change_pct)}
                  </span>
                ) : (
                  <span className="text-[11px] text-zinc-600">no NCCI data</span>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Experience-mod trajectory */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Gauge className="h-4 w-4 text-zinc-500" />
            <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Experience mod trajectory</h3>
          </div>
          <button onClick={() => setShowForm((v) => !v)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors">
            <Plus className="h-3.5 w-3.5" /> Record mod
          </button>
        </div>

        {showForm && (
          <form onSubmit={submitMod} className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-4 p-3 rounded-xl bg-zinc-900/60 border border-zinc-800">
            <div>
              <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Policy start</label>
              <input type="date" value={form.policy_period_start} onChange={(e) => setForm({ ...form, policy_period_start: e.target.value })} className={inputCls} />
            </div>
            <div>
              <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Exp. mod</label>
              <input type="number" step="0.001" placeholder="1.05" value={form.experience_mod} onChange={(e) => setForm({ ...form, experience_mod: e.target.value })} className={inputCls} />
            </div>
            <div>
              <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Carrier</label>
              <input type="text" placeholder="optional" value={form.carrier} onChange={(e) => setForm({ ...form, carrier: e.target.value })} className={inputCls} />
            </div>
            <div>
              <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Annual premium</label>
              <input type="number" step="1" placeholder="optional" value={form.annual_premium} onChange={(e) => setForm({ ...form, annual_premium: e.target.value })} className={inputCls} />
            </div>
            <div className="flex items-end">
              <button type="submit" disabled={saving} className="w-full bg-zinc-100 text-zinc-900 text-sm font-medium rounded-lg px-3 py-1.5 hover:bg-white disabled:opacity-50 transition-colors">
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
            {formErr && <p className="col-span-full text-[11px] text-red-400">{formErr}</p>}
          </form>
        )}

        {detail.mods.length === 0 ? (
          <p className="text-sm text-zinc-500">No experience mods recorded. The mod is the number carriers price WC on &mdash; record it each policy period to track the trajectory.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-800/60">
                  <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Policy period</th>
                  <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Mod</th>
                  <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Carrier</th>
                  <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Premium</th>
                  <th className="pb-2 w-8" />
                </tr>
              </thead>
              <tbody>
                {detail.mods.map((mod) => (
                  <tr key={mod.id} className="border-b border-zinc-800/30 last:border-0">
                    <td className="py-2.5 pr-4 text-zinc-300">{mod.policy_period_start}</td>
                    <td className={`py-2.5 pr-4 text-right font-mono ${mod.experience_mod > 1 ? 'text-red-400' : mod.experience_mod < 1 ? 'text-emerald-400' : 'text-zinc-300'}`}>{mod.experience_mod.toFixed(3)}</td>
                    <td className="py-2.5 pr-4 text-zinc-400 text-xs">{mod.carrier ?? '—'}</td>
                    <td className="py-2.5 pr-4 text-right text-zinc-400 tabular-nums">{mod.annual_premium != null ? `$${mod.annual_premium.toLocaleString()}` : '—'}</td>
                    <td className="py-2.5 text-right">
                      <button onClick={() => removeMod(mod.id)} className="text-zinc-600 hover:text-red-400 transition-colors"><Trash2 className="h-3.5 w-3.5" /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* WC class-code exposures (wcclass01) */}
      <WcClassExposures companyId={companyId} />
    </div>
  )
}

function WcClassExposures({ companyId }: { companyId: string }) {
  const [exposures, setExposures] = useState<WcClassExposure[]>([])
  const [codes, setCodes] = useState<WcClassCode[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ class_code: '', state: '', payroll: '', headcount: '', note: '' })
  const [saving, setSaving] = useState(false)
  const [autoProps, setAutoProps] = useState<ClassAutoMap | null>(null)
  const [autoBusy, setAutoBusy] = useState(false)
  const [savingAll, setSavingAll] = useState(false)
  const inputCls = 'w-full bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500'

  const load = () => { fetchWcClassExposures(companyId).then((r) => setExposures(r.exposures)).catch(() => {}) }
  useEffect(() => {
    load()
    fetchWcClassCodes().then((r) => setCodes(r.class_codes)).catch(() => {})
  }, [companyId])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!form.class_code) return
    setSaving(true)
    try {
      const r = await recordWcClassExposure(companyId, {
        class_code: form.class_code, state: form.state || undefined,
        payroll: form.payroll ? parseFloat(form.payroll) : undefined,
        headcount: form.headcount ? parseInt(form.headcount, 10) : undefined,
        note: form.note || undefined,
      })
      setExposures(r.exposures)
      setForm({ class_code: '', state: '', payroll: '', headcount: '', note: '' }); setShowForm(false)
    } catch { /* leave as-is */ } finally { setSaving(false) }
  }
  const remove = async (id: string) => { try { await deleteWcClassExposure(companyId, id); load() } catch { /* noop */ } }

  const runAutoMap = async () => {
    setAutoBusy(true); setAutoProps(null)
    try { setAutoProps(await autoMapClassExposures(companyId)) } catch { /* noop */ } finally { setAutoBusy(false) }
  }
  const saveAll = async () => {
    if (!autoProps?.proposed.length) return
    setSavingAll(true)
    try {
      for (const p of autoProps.proposed) {
        await recordWcClassExposure(companyId, { class_code: p.class_code, state: p.state, payroll: p.payroll, headcount: p.headcount })
      }
      setAutoProps(null); load()
    } catch { /* leave */ } finally { setSavingAll(false) }
  }

  const totalPremium = exposures.reduce((s, e) => s + (e.est_manual_premium ?? 0), 0)

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <Boxes className="h-4 w-4 text-zinc-500" />
          <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Class-code exposures</h3>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={runAutoMap} disabled={autoBusy} className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 px-2 py-1 rounded-lg border border-emerald-900/60 hover:border-emerald-700 transition-colors disabled:opacity-50">
            <Sparkles className="h-3.5 w-3.5" /> {autoBusy ? 'Mapping…' : 'Auto-map from employees'}
          </button>
          <button onClick={() => setShowForm((v) => !v)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors">
            <Plus className="h-3.5 w-3.5" /> Add class
          </button>
        </div>
      </div>
      <p className="text-[11px] text-zinc-500 mb-3">Payroll by NCCI class drives class-level underwriting. Rates are an illustrative reference seed (pending a licensed NCCI feed); estimated manual premium = payroll ÷ 100 × rate.</p>

      {autoProps && (
        <div className="mb-4 p-3 rounded-xl bg-emerald-950/20 border border-emerald-900/40">
          {autoProps.proposed.length === 0 ? (
            <p className="text-xs text-zinc-400">{autoProps.employee_count === 0 ? 'No employees on file to map.' : 'Could not map any titles to class codes — add manually.'}</p>
          ) : (
            <>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] text-emerald-400 font-medium">AI mapped {autoProps.employee_count} employees → {autoProps.proposed.length} class code(s). Review &amp; save.</span>
                <button onClick={saveAll} disabled={savingAll} className="text-xs bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-3 py-1 disabled:opacity-50">{savingAll ? 'Saving…' : 'Save all'}</button>
              </div>
              <div className="space-y-1">
                {autoProps.proposed.map((p) => (
                  <div key={p.class_code} className="flex items-center gap-3 text-xs py-1 border-b border-zinc-800/30 last:border-0">
                    <span className="font-mono text-zinc-200">{p.class_code}</span>
                    <span className="text-zinc-400 flex-1 truncate">{p.description}</span>
                    <span className="text-zinc-500">{p.headcount} ppl · ${p.payroll.toLocaleString()}</span>
                  </div>
                ))}
                {autoProps.unmapped.length > 0 && <p className="text-[11px] text-amber-400/80 mt-1">{autoProps.unmapped.length} title(s) unmapped — add manually if needed.</p>}
              </div>
            </>
          )}
        </div>
      )}

      {showForm && (
        <form onSubmit={submit} className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-4 p-3 rounded-xl bg-zinc-900/60 border border-zinc-800">
          <div className="md:col-span-2">
            <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Class code</label>
            <select value={form.class_code} onChange={(e) => setForm({ ...form, class_code: e.target.value })} className={inputCls}>
              <option value="">Select…</option>
              {codes.map((c) => <option key={c.class_code} value={c.class_code}>{c.class_code} — {c.description}</option>)}
            </select>
          </div>
          <div><label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">State</label><input maxLength={2} placeholder="US" value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value.toUpperCase() })} className={inputCls} /></div>
          <div><label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Payroll</label><input type="number" step="1000" placeholder="$" value={form.payroll} onChange={(e) => setForm({ ...form, payroll: e.target.value })} className={inputCls} /></div>
          <div><label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Headcount</label><input type="number" placeholder="optional" value={form.headcount} onChange={(e) => setForm({ ...form, headcount: e.target.value })} className={inputCls} /></div>
          <div className="md:col-span-5">
            <button type="submit" disabled={saving} className="bg-zinc-100 text-zinc-900 text-sm font-medium rounded-lg px-4 py-1.5 hover:bg-white disabled:opacity-50 transition-colors">{saving ? 'Saving…' : 'Save'}</button>
          </div>
        </form>
      )}

      {exposures.length === 0 ? (
        <p className="text-sm text-zinc-500">No class-code exposures recorded. Add the client's payroll by NCCI class for class-level underwriting detail.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-800/60">
                <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Class</th>
                <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">State</th>
                <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Payroll</th>
                <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Rate</th>
                <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Est. premium</th>
                <th className="pb-2 w-8" />
              </tr>
            </thead>
            <tbody>
              {exposures.map((e) => (
                <tr key={e.id} className="border-b border-zinc-800/30 last:border-0">
                  <td className="py-2.5 pr-4 text-zinc-300"><span className="font-mono">{e.class_code}</span>{e.description && <span className="text-xs text-zinc-600 ml-2">{e.description}</span>}</td>
                  <td className="py-2.5 pr-4 text-zinc-400">{e.state}</td>
                  <td className="py-2.5 pr-4 text-right text-zinc-400 tabular-nums">{e.payroll != null ? `$${e.payroll.toLocaleString()}` : '—'}</td>
                  <td className="py-2.5 pr-4 text-right text-zinc-400 tabular-nums">{e.base_rate != null ? e.base_rate.toFixed(2) : '—'}</td>
                  <td className="py-2.5 pr-4 text-right font-mono text-zinc-200">{e.est_manual_premium != null ? `$${e.est_manual_premium.toLocaleString()}` : '—'}</td>
                  <td className="py-2.5 text-right"><button onClick={() => remove(e.id)} className="text-zinc-600 hover:text-red-400 transition-colors"><Trash2 className="h-3.5 w-3.5" /></button></td>
                </tr>
              ))}
              {totalPremium > 0 && (
                <tr className="border-t border-zinc-700/60">
                  <td className="py-2.5 pr-4 text-zinc-500 text-xs uppercase tracking-wider" colSpan={4}>Estimated manual premium</td>
                  <td className="py-2.5 pr-4 text-right font-mono text-zinc-100">${totalPremium.toLocaleString()}</td>
                  <td />
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

/* ──────────────────── EPL Readiness Tab ──────────────────── */

const EPL_BAND_TONE: Record<string, string> = {
  strong: 'text-emerald-400',
  adequate: 'text-amber-400',
  developing: 'text-orange-400',
  exposed: 'text-red-400',
}
const EPL_BAND_LABEL: Record<string, string> = {
  strong: 'Strong', adequate: 'Adequate', developing: 'Developing', exposed: 'Exposed',
}
const EPL_STATUS_DOT: Record<string, string> = {
  strong: 'bg-emerald-500', partial: 'bg-amber-500', gap: 'bg-red-500',
}
const EPL_ATTEST_OPTIONS = [
  { value: 'unknown', label: 'Not reviewed' },
  { value: 'in_place', label: 'In place' },
  { value: 'partial', label: 'Partial' },
  { value: 'gap', label: 'Gap' },
]

function EplFactorRow({ f }: { f: EplFactor }) {
  return (
    <div className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
      <span className={`h-2 w-2 rounded-full flex-shrink-0 ${EPL_STATUS_DOT[f.status]}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm text-zinc-200">{f.label}</span>
          <span className="text-[10px] text-zinc-600">{f.weight} pts</span>
        </div>
        <p className="text-[11px] text-zinc-500 truncate">{f.detail}</p>
      </div>
      <span className="text-sm font-mono text-zinc-300 w-10 text-right">{f.score}</span>
    </div>
  )
}

function EplAttestedRow({ f, saving, onSet }: {
  f: EplFactor; saving: boolean; onSet: (s: EplAttestationStatus) => void
}) {
  const status: EplAttestationStatus = f.attestation?.status ?? 'unknown'
  return (
    <div className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
      <span className={`h-2 w-2 rounded-full flex-shrink-0 ${EPL_STATUS_DOT[f.status]}`} />
      <div className="flex-1 min-w-0">
        <span className="text-sm text-zinc-200">{f.label}</span>
        <span className="text-[10px] text-zinc-600 ml-2">{f.weight} pts</span>
      </div>
      <div className="flex items-center gap-2">
        {saving && <Loader2 className="h-3.5 w-3.5 text-zinc-500 animate-spin" />}
        <select
          value={status}
          disabled={saving}
          onChange={(e) => onSet(e.target.value as EplAttestationStatus)}
          className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500"
        >
          {EPL_ATTEST_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>
    </div>
  )
}

function EplTab({ companyId }: { companyId: string }) {
  const [data, setData] = useState<EplReadiness | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [savingKey, setSavingKey] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(false)
    fetchEplClientDetail(companyId)
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [companyId])

  async function setAttestation(key: string, status: EplAttestationStatus) {
    setSavingKey(key)
    try {
      const updated = await recordEplAttestation(companyId, key, { status })
      setData(updated)
    } catch { /* leave prior state on failure */ }
    finally { setSavingKey(null) }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-40"><Loader2 className="h-5 w-5 text-zinc-500 animate-spin" /></div>
  }
  if (error || !data) {
    return <Card className="p-5"><p className="text-sm text-zinc-500">Unable to load EPL readiness.</p></Card>
  }

  const derived = data.factors.filter((f) => f.kind === 'derived')
  const attested = data.factors.filter((f) => f.kind === 'attested')

  return (
    <div className="space-y-4">
      {/* Score header */}
      <Card className="p-5">
        <div className="flex items-center gap-5">
          <div className="text-center flex-shrink-0">
            <div className={`text-5xl font-light font-mono ${EPL_BAND_TONE[data.band]}`}>{data.score}</div>
            <div className={`text-[10px] uppercase tracking-widest font-bold mt-1 ${EPL_BAND_TONE[data.band]}`}>{EPL_BAND_LABEL[data.band]}</div>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-medium text-zinc-200 mb-0.5">EPL Underwriting Readiness</h3>
            <p className="text-[11px] text-zinc-500 mb-3">How this client&rsquo;s HR posture maps to what EPL underwriters ask (WTW IMR 2026).</p>
            <div className="h-2 rounded-full overflow-hidden bg-zinc-800">
              <div className="h-full bg-emerald-500/70" style={{ width: `${data.score}%` }} />
            </div>
            <div className="flex gap-4 mt-2 text-[11px] text-zinc-500">
              <span>From data <span className="font-mono text-zinc-300">{data.derived_score}</span>/{data.derived_max ?? 55}</span>
              <span>Attested <span className="font-mono text-zinc-300">{data.attested_score}</span>/{data.attested_max ?? 45}</span>
            </div>
          </div>
        </div>
      </Card>

      {/* Derived factors */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="h-4 w-4 text-zinc-500" />
          <h3 className="text-sm font-medium text-zinc-200 tracking-wide">From your Matcha data</h3>
        </div>
        <div className="space-y-1">
          {derived.map((f) => <EplFactorRow key={f.key} f={f} />)}
        </div>
      </Card>

      {/* Attested factors */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-1">
          <AlertTriangle className="h-4 w-4 text-zinc-500" />
          <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Underwriter asks &mdash; record during review</h3>
        </div>
        <p className="text-[11px] text-zinc-600 mb-4">Matcha has no data source for these. Set each as you confirm it with the client.</p>
        <div className="space-y-1">
          {attested.map((f) => (
            <EplAttestedRow key={f.key} f={f} saving={savingKey === f.key} onSet={(s) => setAttestation(f.key, s)} />
          ))}
        </div>
      </Card>
    </div>
  )
}

/* ──────────────────── Controls (Proof of Controls) Tab ──────────────────── */

function ControlsTab({ companyId }: { companyId: string }) {
  const [reg, setReg] = useState<ControlsRegister | null>(null)
  const [loading, setLoading] = useState(true)
  const [dl, setDl] = useState(false)

  useEffect(() => {
    fetchClientControls(companyId).then(setReg).catch(() => setReg(null)).finally(() => setLoading(false))
  }, [companyId])

  const tone = (s: string) =>
    s === 'strong' ? 'text-emerald-400' : s === 'partial' ? 'text-amber-400' : s === 'gap' ? 'text-red-400' : 'text-zinc-500'

  if (loading) return <Loader2 className="h-5 w-5 text-zinc-500 animate-spin" />
  if (!reg) return <Card className="p-5"><p className="text-sm text-zinc-500">No controls data.</p></Card>

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-zinc-200">Proof of Controls</h3>
          <p className="text-[11px] text-zinc-500">Auto-derived risk controls. {reg.summary.strong} strong · {reg.summary.gap} gap · {reg.summary.verified}/{reg.summary.total} verified.</p>
        </div>
        <button
          onClick={async () => { setDl(true); try { await downloadClientControls(companyId) } finally { setDl(false) } }}
          disabled={dl}
          className="inline-flex items-center gap-1.5 text-xs text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-1.5 font-medium disabled:opacity-50 shrink-0"
        >
          {dl ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileDown className="h-3.5 w-3.5" />} Controls packet
        </button>
      </div>
      <div className="space-y-1">
        {reg.controls.map((c) => (
          <div key={c.key} className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
            <span className={`text-[10px] font-semibold uppercase w-16 shrink-0 ${tone(c.status)}`}>{c.status}</span>
            <span className="text-sm text-zinc-200 flex-1">{c.label}</span>
            <span className="text-[11px] text-zinc-500 truncate max-w-[40%]">{c.metric ?? '—'}</span>
            {c.verified && <span className="text-[10px] text-emerald-400 shrink-0">verified</span>}
          </div>
        ))}
      </div>
    </Card>
  )
}

/* ──────────────────── Defense Files (claims-readiness) Tab ──────────────────── */

function DefenseTab({ companyId }: { companyId: string }) {
  const [incidents, setIncidents] = useState<DefenseIncident[]>([])
  const [cases, setCases] = useState<DefenseErCase[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.allSettled([
      fetchClientDefenseIncidents(companyId).then((r) => setIncidents(r.incidents)),
      fetchClientDefenseErCases(companyId).then((r) => setCases(r.cases)),
    ]).finally(() => setLoading(false))
  }, [companyId])

  if (loading) return <Loader2 className="h-5 w-5 text-zinc-500 animate-spin" />

  return (
    <div className="space-y-4">
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 mb-1">Incident defense files</h3>
        <p className="text-[11px] text-zinc-500 mb-3">Per-incident claims-readiness packets — timeline, witnesses, policy map, corrective actions.</p>
        {incidents.length === 0 ? <p className="text-sm text-zinc-500">No incidents on file.</p> : (
          <div className="space-y-1">
            {incidents.map((i) => (
              <div key={i.id} className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
                <span className="text-[11px] text-zinc-500 w-24 shrink-0">{i.incident_number ?? '—'}</span>
                <span className="text-sm text-zinc-200 flex-1 truncate">{i.title ?? 'Incident'}</span>
                <span className="text-[11px] text-zinc-500">{i.severity ?? ''}</span>
                <button onClick={() => downloadDefenseIncident(companyId, i.id, i.incident_number)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-emerald-400 px-2 py-1 rounded-lg border border-zinc-700"><Download className="h-3.5 w-3.5" /> PDF</button>
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 mb-1">ER case defense files</h3>
        <p className="text-[11px] text-zinc-500 mb-3">Per-case defense packets — timeline, notes, documents, determination.</p>
        {cases.length === 0 ? <p className="text-sm text-zinc-500">No ER cases on file.</p> : (
          <div className="space-y-1">
            {cases.map((c) => (
              <div key={c.id} className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
                <span className="text-[11px] text-zinc-500 w-24 shrink-0">{c.case_number ?? '—'}</span>
                <span className="text-sm text-zinc-200 flex-1 truncate">{c.title ?? 'Case'}</span>
                <span className="text-[11px] text-zinc-500">{c.status ?? ''}</span>
                <button onClick={() => downloadDefenseErCase(companyId, c.id, c.case_number)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-emerald-400 px-2 py-1 rounded-lg border border-zinc-700"><Download className="h-3.5 w-3.5" /> PDF</button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
