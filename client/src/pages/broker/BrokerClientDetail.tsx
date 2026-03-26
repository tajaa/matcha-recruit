import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft, MapPin, FileText, Shield, AlertTriangle,
  Clock, Building2, Users, Loader2, AlertCircle,
} from 'lucide-react'
import { Card } from '../../components/ui'
import { StatCard } from '../../components/dashboard'
import { fetchBrokerClientDetail } from '../../api/broker'
import type { BrokerClientDetailResponse } from '../../types/broker'

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

type Tab = 'overview' | 'compliance' | 'policies' | 'ir_er' | 'activity'

const tabs: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'compliance', label: 'Compliance' },
  { key: 'policies', label: 'Policies & Handbooks' },
  { key: 'ir_er', label: 'IR / ER' },
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
