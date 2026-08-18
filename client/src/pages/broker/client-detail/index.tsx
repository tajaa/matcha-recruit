import { useState, useEffect, type ReactNode } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Clock, AlertTriangle, Users, Loader2, AlertCircle, type LucideIcon } from 'lucide-react'
import {
  fetchBrokerClientDetail, downloadTenantSubmission, fetchTenantCoverageGap,
  fetchTenantSubmissionPreview, fetchTenantSubmissionNotes, saveTenantSubmissionNotes,
  fetchClientLossRatio, recordClientLossPremium, fetchWcClientDetail,
} from '../../../api/broker/broker'
import { SubmissionPanel } from '../../../components/broker/SubmissionPanel'
import { IRPremiumImpactCard } from '../../../components/ir/risk/IRPremiumImpactCard'
import { RenewalPill } from '../../../components/broker/RenewalPill'
import { daysUntilDate, fmtDate } from '../../../utils/broker/brokerFormat'
import type { BrokerClientDetailResponse, WcClientDetailResponse } from '../../../types/broker'
import { riskColors, riskLabels } from './shared'
import { PoliciesTab } from './PoliciesTab'
import { IRERTab } from './IRERTab'
import { WcTab } from './WcTab'
import { LossTriangleTab } from './LossTriangleTab'
import { LossRatioTab } from './LossRatioTab'
import { EplTab } from './EplTab'
import { ControlsTab } from './ControlsTab'
import { LimitsTab } from './LimitsTab'
import { DefenseTab } from './DefenseTab'
import { InsuranceTab } from './InsuranceTab'
import { PilotTab } from '../pilot/PilotTab'

export { LossRatioTab } from './LossRatioTab'
export { LossTriangleTab } from './LossTriangleTab'
export type { LossDevApi } from './LossTriangleTab'

function SummaryCard({ label, icon: Icon, value, sub, urgent }: {
  label: string
  icon: LucideIcon
  value: ReactNode
  sub?: ReactNode
  urgent?: boolean
}) {
  return (
    <div className={`relative overflow-hidden rounded-xl border bg-zinc-900/60 p-5 ${
      urgent ? 'ring-1 ring-red-500/30 border-red-900/40' : 'border-zinc-800/60'
    }`}>
      <Icon className="absolute -top-1.5 -right-1.5 h-16 w-16 text-zinc-800/30" />
      <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider">{label}</p>
      <div className="mt-1.5 min-h-9 flex items-center text-2xl font-semibold text-zinc-100 tabular-nums">
        {value}
      </div>
      {sub && <div className="text-[11px] text-zinc-500 mt-1">{sub}</div>}
    </div>
  )
}

type Tab = 'wc' | 'loss_analysis' | 'epl_controls' | 'claims' | 'coverage_limits' | 'submission' | 'pilot'

const tabs: { key: Tab; label: string }[] = [
  { key: 'wc', label: "Workers' Comp" },
  { key: 'loss_analysis', label: 'Loss Analysis' },
  { key: 'epl_controls', label: 'EPL & Controls' },
  { key: 'claims', label: 'Claims' },
  { key: 'coverage_limits', label: 'Coverage & Limits' },
  { key: 'submission', label: 'Submission' },
  { key: 'pilot', label: 'Pilot' },
]

export default function BrokerClientDetail() {
  const { companyId } = useParams<{ companyId: string }>()
  const [data, setData] = useState<BrokerClientDetailResponse | null>(null)
  const [wcDetail, setWcDetail] = useState<WcClientDetailResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>('wc')

  useEffect(() => {
    if (!companyId) return
    setLoading(true)
    fetchBrokerClientDetail(companyId)
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
    // WC metrics carry the premium-impact estimate (same shape as the client-side
    // Risk Insights page). Best-effort: a failure or an absent estimate just hides
    // the card, so it never blocks the rest of the drill-down.
    setWcDetail(null)
    fetchWcClientDetail(companyId)
      .then(setWcDetail)
      .catch(() => setWcDetail(null))
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

  const { company, compliance, policies, ir_summary, er_summary, handbooks } = data

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
            {[company.industry, company.size, company.link_status].filter(Boolean).join(' · ')}
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 text-xs text-zinc-300 px-2.5 py-1 rounded-full bg-zinc-800 border border-zinc-700">
          <span className={`h-2 w-2 rounded-full ${riskColors[company.risk_signal] ?? 'bg-zinc-600'}`} />
          {riskLabels[company.risk_signal] ?? company.risk_signal}
        </span>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SummaryCard
          label="Headcount & Locations"
          icon={Users}
          value={company.active_employee_count}
          sub={`${compliance.total_locations} active location${compliance.total_locations === 1 ? '' : 's'}`}
        />
        <SummaryCard
          label="Days to Renewal"
          icon={Clock}
          value={
            <RenewalPill
              days={daysUntilDate(company.renewal_date)}
              derived={company.renewal_date_source === 'coverage'}
            />
          }
          sub={company.renewal_date ? fmtDate(company.renewal_date) : 'No renewal date on file'}
        />
        <SummaryCard
          label="Active Open Exposure"
          icon={AlertTriangle}
          value={`${ir_summary.total_open} incidents · ${er_summary.total_open} ER`}
          sub="active open exposure"
          urgent={ir_summary.total_open + er_summary.total_open > 0}
        />
      </div>

      {/* Premium impact estimate — headline WC renewal-premium signal, mirrored
          from the client-side Risk Insights page. Hidden when there's no estimate. */}
      {wcDetail?.metrics.premium_impact && (
        <IRPremiumImpactCard metrics={wcDetail.metrics} />
      )}

      {/* Tab bar */}
      <div className="flex gap-1 overflow-x-auto border-b border-zinc-800">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className={`shrink-0 px-4 py-2.5 text-sm font-medium transition-colors ${
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
      {activeTab === 'wc' && companyId && <WcTab companyId={companyId} />}
      {activeTab === 'loss_analysis' && companyId && (
        <div className="space-y-4">
          <LossTriangleTab companyId={companyId} />
          <LossRatioTab
            subjectId={companyId}
            fetchData={() => fetchClientLossRatio(companyId)}
            savePremium={(b) => recordClientLossPremium(companyId, b)}
          />
        </div>
      )}
      {activeTab === 'epl_controls' && companyId && (
        <div className="space-y-4">
          <EplTab companyId={companyId} />
          <ControlsTab companyId={companyId} />
        </div>
      )}
      {activeTab === 'claims' && (
        <div className="space-y-4">
          <IRERTab ir={ir_summary} er={er_summary} />
          {companyId && <DefenseTab companyId={companyId} />}
        </div>
      )}
      {activeTab === 'coverage_limits' && companyId && (
        <div className="space-y-4">
          <InsuranceTab companyId={companyId} />
          <PoliciesTab policies={policies} handbooks={handbooks} />
          <LimitsTab companyId={companyId} />
        </div>
      )}
      {activeTab === 'submission' && companyId && (
        <SubmissionPanel
          onDownload={() => downloadTenantSubmission(companyId)}
          onAnalyze={() => fetchTenantCoverageGap(companyId)}
          loadPreview={() => fetchTenantSubmissionPreview(companyId)}
          loadNotes={() => fetchTenantSubmissionNotes(companyId)}
          saveNotes={(n) => saveTenantSubmissionNotes(companyId, n)}
        />
      )}
      {activeTab === 'pilot' && companyId && <PilotTab subjectKind="company" subjectId={companyId} />}
    </div>
  )
}
