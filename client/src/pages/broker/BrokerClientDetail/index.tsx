import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, FileText, Shield, AlertTriangle, Users, Loader2, AlertCircle } from 'lucide-react'
import { StatCard } from '../../../components/dashboard'
import {
  fetchBrokerClientDetail, downloadTenantSubmission, fetchTenantCoverageGap,
  fetchTenantSubmissionPreview, fetchTenantSubmissionNotes, saveTenantSubmissionNotes,
  fetchClientLossRatio, recordClientLossPremium,
} from '../../../api/broker'
import { SubmissionPanel } from '../../../components/broker/SubmissionPanel'
import type { BrokerClientDetailResponse } from '../../../types/broker'
import { riskColors, riskLabels } from './shared'
import { OverviewTab } from './OverviewTab'
import { ComplianceTab } from './ComplianceTab'
import { PoliciesTab } from './PoliciesTab'
import { IRERTab } from './IRERTab'
import { ActivityTab } from './ActivityTab'
import { WcTab } from './WcTab'
import { LossTriangleTab } from './LossTriangleTab'
import { LossRatioTab } from './LossRatioTab'
import { EplTab } from './EplTab'
import { ControlsTab } from './ControlsTab'
import { LimitsTab } from './LimitsTab'
import { DefenseTab } from './DefenseTab'

export { LossRatioTab } from './LossRatioTab'

type Tab = 'overview' | 'compliance' | 'policies' | 'ir_er' | 'wc' | 'loss_dev' | 'loss_ratio' | 'epl' | 'controls' | 'limits' | 'defense' | 'submission' | 'activity'

const tabs: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'compliance', label: 'Compliance' },
  { key: 'policies', label: 'Policies & Handbooks' },
  { key: 'ir_er', label: 'IR / ER' },
  { key: 'wc', label: "Workers' Comp" },
  { key: 'loss_dev', label: 'Loss Triangle' },
  { key: 'loss_ratio', label: 'Loss Ratio' },
  { key: 'epl', label: 'EPL Readiness' },
  { key: 'controls', label: 'Controls' },
  { key: 'limits', label: 'Limits' },
  { key: 'defense', label: 'Defense Files' },
  { key: 'submission', label: 'Submission' },
  { key: 'activity', label: 'Activity' },
]

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
            {[company.industry, company.size, company.link_status].filter(Boolean).join(' · ')}
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
      {activeTab === 'loss_dev' && companyId && <LossTriangleTab companyId={companyId} />}
      {activeTab === 'loss_ratio' && companyId && (
        <LossRatioTab
          subjectId={companyId}
          fetchData={() => fetchClientLossRatio(companyId)}
          savePremium={(b) => recordClientLossPremium(companyId, b)}
        />
      )}
      {activeTab === 'epl' && companyId && <EplTab companyId={companyId} />}
      {activeTab === 'controls' && companyId && <ControlsTab companyId={companyId} />}
      {activeTab === 'limits' && companyId && <LimitsTab companyId={companyId} />}
      {activeTab === 'defense' && companyId && <DefenseTab companyId={companyId} />}
      {activeTab === 'submission' && companyId && (
        <SubmissionPanel
          onDownload={() => downloadTenantSubmission(companyId)}
          onAnalyze={() => fetchTenantCoverageGap(companyId)}
          loadPreview={() => fetchTenantSubmissionPreview(companyId)}
          loadNotes={() => fetchTenantSubmissionNotes(companyId)}
          saveNotes={(n) => saveTenantSubmissionNotes(companyId, n)}
        />
      )}
      {activeTab === 'activity' && <ActivityTab activity={recent_activity} />}
    </div>
  )
}
