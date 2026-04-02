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
import { SeparationRiskCard } from '../../components/risk-assessment/SeparationRiskCard'
import { ERCaseMetricsPanel } from '../../components/risk-assessment/ERCaseMetricsPanel'
import { BAND_COLOR, BAND_LABEL, type Band } from '../../types/risk-assessment'
import { useMonteCarloData } from '../../hooks/risk-assessment/useMonteCarloData'
import { LossDistributionPanel } from '../../components/risk-assessment/LossDistributionPanel'
import { ExceedanceCurvePanel } from '../../components/risk-assessment/ExceedanceCurvePanel'
import { DimensionCorrelationPanel } from '../../components/risk-assessment/DimensionCorrelationPanel'
import { TailAnalysisPanel } from '../../components/risk-assessment/TailAnalysisPanel'
import { EnhancedBenchmarksPanel } from '../../components/risk-assessment/EnhancedBenchmarksPanel'
import { EnhancedCohortPanel } from '../../components/risk-assessment/EnhancedCohortPanel'

export default function RiskAssessment() {
  const [tab, setTab] = useState<'overview' | 'analytics' | 'quantitative'>('overview')
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
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading risk assessment...</div>
      </div>
    )
  }

  // ─── No Snapshot ────────────────────────────────────────────────────────────

  if (noSnapshot) {
    return (
      <div>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-zinc-100">Risk Assessment</h1>
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
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Risk Assessment</h1>
          <p className="mt-1 text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
            Computed {new Date(a.computed_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
          </p>
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
      <div className="flex gap-0 border border-zinc-700 rounded-xl overflow-hidden w-fit">
        {(['overview', 'analytics', 'quantitative'] as const).map((t) => (
          <button
            key={t}
            className={`px-5 py-2 text-[11px] uppercase tracking-widest font-bold transition-colors ${
              tab === t
                ? 'bg-zinc-800 text-zinc-50'
                : 'bg-zinc-900 text-zinc-500 hover:text-zinc-300'
            }`}
            onClick={() => setTab(t)}
          >
            {t === 'overview' ? 'Overview' : t === 'analytics' ? 'Analytics' : 'Quantitative'}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {tab === 'overview' && (
        <div className="space-y-8">
          <RiskScoreCard
            score={a.overall_score}
            band={a.overall_band}
            report={a.report}
            dimensions={a.dimensions}
            weights={a.weights}
          />

          {/* Risk Trend Chart */}
          <ScoreHistoryPanel qs={qs} dimensionKeys={Object.keys(a.dimensions)} />

          {/* Dimension Breakdown */}
          <RiskDimensionsGrid dimensions={a.dimensions} weights={a.weights} />

          {/* Separation Risk Analytics */}
          <SeparationRiskCard />

          {/* Action Items */}
          <ActionItemsSection qs={qs} assessment={a} />

          {/* ER Case Metrics */}
          <ERCaseMetricsPanel />

          {/* Consultation Analysis */}
          {(a.report || (a.recommendations && a.recommendations.length > 0)) && (
            <RecommendationsSection
              recommendations={a.recommendations ?? []}
              report={a.report}
            />
          )}

          {/* Score Bands Legend */}
          <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-4">Score Bands</div>
            <div className="grid grid-cols-4 gap-px bg-white/10 rounded-lg overflow-hidden">
              {(['low', 'moderate', 'high', 'critical'] as Band[]).map(band => (
                <div key={band} className="bg-zinc-800 px-4 py-3">
                  <div className={`text-[10px] font-bold uppercase tracking-widest ${BAND_COLOR[band].text}`}>{BAND_LABEL[band]}</div>
                  <div className="text-[9px] text-zinc-600 mt-1 font-mono">
                    {band === 'low' ? '0 – 25' : band === 'moderate' ? '26 – 50' : band === 'high' ? '51 – 75' : '76 – 100'}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Analytics Tab */}
      {tab === 'analytics' && (
        <div className="space-y-6">
          <MonteCarloPanel qs={qs} isAdmin={isAdmin} companyId={selectedCompanyId} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <CohortAnalysisPanel qs={qs} />
            <BenchmarksPanel qs={qs} />
          </div>
          <AnomaliesPanel qs={qs} />
        </div>
      )}

      {/* Quantitative Tab */}
      {tab === 'quantitative' && (
        <QuantitativeTab qs={qs} isAdmin={isAdmin} />
      )}
    </div>
  )
}

function QuantitativeTab({ qs, isAdmin }: { qs: string; isAdmin: boolean }) {
  const { data: mc, loading, error, reload } = useMonteCarloData(qs)

  return (
    <div className="space-y-6">
      {loading && (
        <div className="text-xs text-zinc-500 animate-pulse py-8 text-center">Loading quantitative analytics...</div>
      )}
      {!loading && mc && (
        <>
          <LossDistributionPanel mc={mc} isAdmin={isAdmin} onRerun={reload} />
          <ExceedanceCurvePanel mc={mc} />
        </>
      )}
      {!loading && error && (
        <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 text-sm text-zinc-500 text-center">
          {error}
          {isAdmin && (
            <button onClick={reload} className="ml-2 text-zinc-400 hover:text-zinc-200 transition-colors underline">
              Retry
            </button>
          )}
        </div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <DimensionCorrelationPanel qs={qs} />
        <TailAnalysisPanel qs={qs} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <EnhancedCohortPanel qs={qs} />
        <EnhancedBenchmarksPanel qs={qs} />
      </div>
    </div>
  )
}
