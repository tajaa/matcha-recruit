import { useState } from 'react'
import { Button, Select } from '../../components/ui'
import { useRiskAssessment } from '../../hooks/risk-assessment/useRiskAssessment'
import { RiskScoreCard } from '../../components/risk-assessment/RiskScoreCard'
import { RiskDimensionsGrid } from '../../components/risk-assessment/RiskDimensionsGrid'
import { RecommendationsSection } from '../../components/risk-assessment/RecommendationsSection'
import { ActionItemsSection } from '../../components/risk-assessment/ActionItemsSection'
import { ScoreHistoryPanel } from '../../components/risk-assessment/ScoreHistoryPanel'
import { MonteCarloPanel } from '../../components/risk-assessment/MonteCarloPanel'
import { CohortAnalysisPanel } from '../../components/risk-assessment/CohortAnalysisPanel'
import { BenchmarksPanel } from '../../components/risk-assessment/BenchmarksPanel'
import { AnomaliesPanel } from '../../components/risk-assessment/AnomaliesPanel'
import { fmt, capitalize } from '../../types/risk-assessment'

export default function RiskAssessment() {
  const [tab, setTab] = useState<'overview' | 'analytics'>('overview')
  const {
    assessment,
    loading,
    noSnapshot,
    isAdmin,
    companies,
    selectedCompanyId,
    setSelectedCompanyId,
    running,
    handleRunAssessment,
    qs,
  } = useRiskAssessment()

  // ─── Loading ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">Risk Assessment</h1>
        <p className="mt-4 text-sm text-zinc-500">Loading...</p>
      </div>
    )
  }

  // ─── No Snapshot ────────────────────────────────────────────────────────────

  if (noSnapshot) {
    return (
      <div>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">Risk Assessment</h1>
            <p className="mt-1 text-sm text-zinc-500">Holistic workforce risk scoring across compliance, incidents, ER cases, and more.</p>
          </div>
          {isAdmin && companies.length > 0 && (
            <Select
              label=""
              options={companies.map((c) => ({ value: c.id, label: c.company_name }))}
              value={selectedCompanyId ?? ''}
              onChange={(e) => setSelectedCompanyId(e.target.value)}
            />
          )}
        </div>
        <div className="mt-16 flex flex-col items-center justify-center text-center">
          <p className="text-zinc-400 text-base mb-4">No risk assessment data yet.</p>
          {isAdmin ? (
            <Button onClick={handleRunAssessment} disabled={running || !selectedCompanyId}>
              {running ? 'Running...' : `Run Assessment${selectedCompanyId ? ` for ${companies.find((c) => c.id === selectedCompanyId)?.company_name ?? ''}` : ''}`}
            </Button>
          ) : (
            <p className="text-sm text-zinc-500">Contact your account manager to run an assessment.</p>
          )}
        </div>
      </div>
    )
  }

  // ─── Full Page ──────────────────────────────────────────────────────────────

  const a = assessment!

  return (
    <div>
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">Risk Assessment</h1>
          <p className="mt-1 text-sm text-zinc-500">Last computed {fmt(a.computed_at)}</p>
        </div>
        {isAdmin && (
          <div className="flex items-center gap-3">
            {companies.length > 0 && (
              <Select
                label=""
                options={companies.map((c) => ({ value: c.id, label: c.company_name }))}
                value={selectedCompanyId ?? ''}
                onChange={(e) => {
                  setSelectedCompanyId(e.target.value)
                  setTab('overview')
                }}
              />
            )}
            <Button onClick={handleRunAssessment} disabled={running} size="sm">
              {running ? 'Running...' : 'Run Assessment'}
            </Button>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 mt-4 mb-5">
        {(['overview', 'analytics'] as const).map((t) => (
          <Button
            key={t}
            variant={tab === t ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setTab(t)}
          >
            {capitalize(t)}
          </Button>
        ))}
      </div>

      {/* Overview Tab */}
      {tab === 'overview' && (
        <div className="space-y-6">
          <RiskScoreCard score={a.overall_score} band={a.overall_band} report={a.report} />
          <RiskDimensionsGrid dimensions={a.dimensions} />
          {a.recommendations && a.recommendations.length > 0 && (
            <RecommendationsSection recommendations={a.recommendations} />
          )}
          <ActionItemsSection qs={qs} />
        </div>
      )}

      {/* Analytics Tab */}
      {tab === 'analytics' && (
        <div className="space-y-8">
          <ScoreHistoryPanel qs={qs} dimensionKeys={Object.keys(a.dimensions)} />
          <MonteCarloPanel qs={qs} isAdmin={isAdmin} companyId={selectedCompanyId} />
          <CohortAnalysisPanel qs={qs} />
          <BenchmarksPanel qs={qs} />
          <AnomaliesPanel qs={qs} />
        </div>
      )}
    </div>
  )
}
