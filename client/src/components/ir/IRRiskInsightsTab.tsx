import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react'
import { api } from '../../api/client'
import { Button, Select } from '../ui'
import type {
  IRRiskInsights,
  IRRiskMatrix,
  IRAnalyticsSummary,
} from '../../types/ir'
import { synthesizeAssessment } from './risk/synth'
import { IRRiskHeroCard } from './risk/IRRiskHeroCard'
import { IRDimensionsGrid } from './risk/IRDimensionsGrid'
import { IRRiskMatrixHeatmap } from './risk/IRRiskMatrixHeatmap'
import { IRThemeCard } from './risk/IRThemeCard'
import { IRWcMetricsCard, type WcMetrics } from './risk/IRWcMetricsCard'
import { IRIncidentTrendChart } from './risk/IRIncidentTrendChart'
import { IRPremiumImpactCard } from './risk/IRPremiumImpactCard'
import { IRQuarterlyRecordableChart } from './risk/IRQuarterlyRecordableChart'
import { IRSeverityDonut } from './risk/IRSeverityDonut'
import { IRPeopleCard } from './risk/IRPeopleCard'

type LocationRow = {
  id: string
  name: string | null
  city: string
  state: string
  is_active: boolean
}

type Props = {
  onNavigateIncident?: (id: string) => void
}

const DAYS_OPTIONS = [
  { value: '30', label: 'Last 30 days' },
  { value: '60', label: 'Last 60 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '180', label: 'Last 180 days' },
]

function formatLocationLabel(loc: LocationRow): string {
  const name = (loc.name || '').trim()
  const place = [loc.city, loc.state].filter(Boolean).join(', ')
  if (name && place) return `${name} — ${place}`
  return name || place || loc.id.slice(0, 8)
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  const diffMs = Date.now() - then
  const min = Math.floor(diffMs / 60000)
  if (min < 1) return 'just now'
  if (min < 60) return `${min} min ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  const day = Math.floor(hr / 24)
  return `${day}d ago`
}

export function IRRiskInsightsTab({ onNavigateIncident }: Props) {
  const [locations, setLocations] = useState<LocationRow[] | null>(null)
  const [locationFilter, setLocationFilter] = useState<string>('')
  const [days, setDays] = useState<string>('90')

  const [matrix, setMatrix] = useState<IRRiskMatrix | null>(null)
  const [matrixLoading, setMatrixLoading] = useState(false)
  const [matrixError, setMatrixError] = useState<string | null>(null)

  const [insights, setInsights] = useState<IRRiskInsights | null>(null)
  const [insightsLoading, setInsightsLoading] = useState(false)
  const [insightsError, setInsightsError] = useState<string | null>(null)

  const [wcMetrics, setWcMetrics] = useState<WcMetrics | null>(null)
  const [summary, setSummary] = useState<IRAnalyticsSummary | null>(null)

  useEffect(() => {
    api.get<LocationRow[]>('/ir-onboarding/locations')
      .then((rows) => setLocations(rows || []))
      .catch(() => setLocations([]))
  }, [])

  function buildMatrixQs(): string {
    const p = new URLSearchParams()
    if (locationFilter) p.set('location_id', locationFilter)
    p.set('days', days)
    return p.toString()
  }

  async function loadMatrix() {
    setMatrixLoading(true)
    setMatrixError(null)
    try {
      const res = await api.get<IRRiskMatrix>(`/ir/incidents/analytics/risk-matrix?${buildMatrixQs()}`)
      setMatrix(res)
    } catch (e) {
      setMatrixError(e instanceof Error ? e.message : 'Failed to load risk matrix')
    } finally {
      setMatrixLoading(false)
    }
  }

  async function loadInsights(opts?: { regenerate?: boolean }) {
    setInsightsLoading(true)
    setInsightsError(null)
    try {
      const p = new URLSearchParams()
      if (locationFilter) p.set('location_id', locationFilter)
      p.set('days', days)
      if (opts?.regenerate) p.set('regenerate', 'true')
      const res = await api.get<IRRiskInsights>(`/ir/incidents/analytics/risk-insights?${p.toString()}`)
      setInsights(res)
    } catch (e) {
      setInsightsError(e instanceof Error ? e.message : 'Failed to load risk insights')
    } finally {
      setInsightsLoading(false)
    }
  }

  useEffect(() => {
    loadMatrix()
    loadInsights()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locationFilter, days])

  useEffect(() => {
    api.get<WcMetrics>('/ir/incidents/analytics/wc-metrics?period_days=365')
      .then(setWcMetrics)
      .catch(() => setWcMetrics(null))
    api.get<IRAnalyticsSummary>('/ir/incidents/analytics/summary')
      .then(setSummary)
      .catch(() => setSummary(null))
  }, [])

  const locationOptions = useMemo(() => {
    const active = (locations || []).filter((l) => l.is_active)
    return [
      { value: '', label: 'All locations' },
      ...active.map((l) => ({ value: l.id, label: formatLocationLabel(l) })),
    ]
  }, [locations])

  const assessment = useMemo(
    () => synthesizeAssessment(matrix, insights),
    [matrix, insights],
  )

  const fullyLoading = matrixLoading && !matrix

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Risk Insights</h1>
          {assessment && (
            <p className="mt-1 text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
              Computed {new Date(assessment.computed_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-48">
            <Select
              label=""
              options={locationOptions}
              value={locationFilter}
              onChange={(e) => setLocationFilter(e.target.value)}
            />
          </div>
          <div className="w-36">
            <Select
              label=""
              options={DAYS_OPTIONS}
              value={days}
              onChange={(e) => setDays(e.target.value)}
            />
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => loadInsights({ regenerate: true })}
            disabled={insightsLoading}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${insightsLoading ? 'animate-spin' : ''}`} />
            <span className="ml-2">Regenerate</span>
          </Button>
        </div>
      </div>

      {fullyLoading ? (
        <div className="flex items-center justify-center min-h-[40vh]">
          <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading risk insights…</div>
        </div>
      ) : matrixError ? (
        <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 text-sm text-red-400">{matrixError}</div>
      ) : !assessment || matrix?.company_total === 0 ? (
        <div className="bg-zinc-900 border border-white/10 rounded-2xl p-12 text-center">
          <p className="text-sm text-zinc-400 mb-1">No incidents in this window.</p>
          <p className="text-[11px] text-zinc-600">
            Once incidents are reported, scores and themes will appear here.
          </p>
        </div>
      ) : (
        <>
          <IRRiskHeroCard assessment={assessment} periodDays={matrix?.period_days ?? days} />

          <IRRiskMatrixHeatmap matrix={matrix} loading={matrixLoading} error={matrixError} />

          <IRIncidentTrendChart />

          {wcMetrics && <IRWcMetricsCard metrics={wcMetrics} />}

          {wcMetrics?.premium_impact && <IRPremiumImpactCard metrics={wcMetrics} />}

          {wcMetrics && wcMetrics.quarterly.length > 0 && (
            <IRQuarterlyRecordableChart quarterly={wcMetrics.quarterly} />
          )}

          <IRSeverityDonut summary={summary} />

          <IRDimensionsGrid assessment={assessment} />

          {/* AI Themes */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="flex items-center gap-2 text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
                <AlertTriangle className="w-3.5 h-3.5" />
                Intelligent Theme Analysis · last {insights?.period_days ?? days} days
              </h2>
              {insights && (
                <span className="text-[10px] text-zinc-600 font-mono">
                  {insights.from_cache ? 'cached' : 'fresh'} · {relativeTime(insights.generated_at)}
                </span>
              )}
            </div>
            {insightsLoading && !insights ? (
              <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 flex items-center justify-center text-zinc-500">
                <Loader2 className="w-4 h-4 animate-spin" />
              </div>
            ) : insightsError ? (
              <p className="text-sm text-red-400">{insightsError}</p>
            ) : !insights || insights.themes.length === 0 ? (
              <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 text-sm text-zinc-500 text-center">
                No recurring patterns detected. Themes need ≥3 supporting incidents to surface.
              </div>
            ) : (
              <div className="grid gap-4 grid-cols-1 lg:grid-cols-2">
                {insights.themes.map((t, idx) => (
                  <IRThemeCard
                    key={`${t.label}-${idx}`}
                    theme={t}
                    onNavigateIncident={onNavigateIncident}
                  />
                ))}
              </div>
            )}
          </section>

          <IRPeopleCard />

          {/* Upgrade footer */}
          <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div>
              <div className="text-sm font-medium text-zinc-100">Want a holistic risk score?</div>
              <p className="text-xs text-zinc-500 mt-1 leading-relaxed">
                Matcha Platform adds compliance, ER cases, workforce, and legislative dimensions for a full 0–100 risk assessment.
              </p>
            </div>
            <a
              href="mailto:hello@matcha.work?subject=Upgrade%20to%20Matcha%20Platform"
              className="text-xs font-medium text-emerald-400 hover:text-emerald-300 underline underline-offset-2 whitespace-nowrap"
            >
              Talk to sales →
            </a>
          </div>
        </>
      )}
    </div>
  )
}
