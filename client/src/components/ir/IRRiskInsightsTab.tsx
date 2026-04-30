import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react'
import { api } from '../../api/client'
import { Badge, Button, Select } from '../ui'
import {
  SEVERITY_BADGE,
  severityLabel,
  type IRIncidentType,
  type IRRiskInsights,
  type IRRiskMatrix,
  type IRRiskMatrixCell,
  type IRRiskTheme,
} from '../../types/ir'

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

const TYPE_COLUMNS: { key: IRIncidentType; label: string }[] = [
  { key: 'safety', label: 'Safety' },
  { key: 'behavioral', label: 'Behavioral' },
  { key: 'property', label: 'Property' },
  { key: 'near_miss', label: 'Near Miss' },
  { key: 'other', label: 'Other' },
]

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
  const [locationFilter, setLocationFilter] = useState<string>('') // '' = all
  const [days, setDays] = useState<string>('30')
  const [insightDays, setInsightDays] = useState<string>('30')

  const [matrix, setMatrix] = useState<IRRiskMatrix | null>(null)
  const [matrixLoading, setMatrixLoading] = useState(false)
  const [matrixError, setMatrixError] = useState<string | null>(null)

  const [insights, setInsights] = useState<IRRiskInsights | null>(null)
  const [insightsLoading, setInsightsLoading] = useState(false)
  const [insightsError, setInsightsError] = useState<string | null>(null)

  useEffect(() => {
    api.get<LocationRow[]>('/ir-onboarding/locations')
      .then((rows) => setLocations(rows || []))
      .catch(() => setLocations([]))
  }, [])

  function buildQs(extra?: Record<string, string | undefined>): string {
    const p = new URLSearchParams()
    if (locationFilter) p.set('location_id', locationFilter)
    p.set('days', days)
    if (extra) {
      for (const [k, v] of Object.entries(extra)) {
        if (v != null) p.set(k, v)
      }
    }
    return p.toString()
  }

  async function loadMatrix() {
    setMatrixLoading(true)
    setMatrixError(null)
    try {
      const res = await api.get<IRRiskMatrix>(`/ir/incidents/analytics/risk-matrix?${buildQs()}`)
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
      p.set('days', insightDays)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locationFilter, days])

  useEffect(() => {
    loadInsights()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locationFilter, insightDays])

  const locationOptions = useMemo(() => {
    const active = (locations || []).filter((l) => l.is_active)
    return [
      { value: '', label: 'All locations' },
      ...active.map((l) => ({ value: l.id, label: formatLocationLabel(l) })),
    ]
  }, [locations])

  const totalsRow = useMemo(() => {
    if (!matrix) return null
    const totals: Record<string, number> = {}
    let grand = 0
    for (const r of matrix.rows) {
      for (const c of r.cells) {
        totals[c.incident_type] = (totals[c.incident_type] || 0) + c.count
        grand += c.count
      }
    }
    return { totals, grand }
  }, [matrix])

  return (
    <div className="space-y-6">
      {/* Filter bar */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-56">
          <Select
            label="Location"
            options={locationOptions}
            value={locationFilter}
            onChange={(e) => setLocationFilter(e.target.value)}
          />
        </div>
        <div className="w-44">
          <Select
            label="Matrix window"
            options={DAYS_OPTIONS}
            value={days}
            onChange={(e) => setDays(e.target.value)}
          />
        </div>
        <div className="w-44">
          <Select
            label="Insights window"
            options={DAYS_OPTIONS}
            value={insightDays}
            onChange={(e) => setInsightDays(e.target.value)}
          />
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => loadInsights({ regenerate: true })}
          disabled={insightsLoading}
        >
          <RefreshCw className={`w-4 h-4 ${insightsLoading ? 'animate-spin' : ''}`} />
          <span className="ml-2">Regenerate insights</span>
        </Button>
      </div>

      {/* Risk Matrix */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
            Risk Matrix · last {matrix?.period_days ?? days} days
          </h2>
          {matrix && (
            <span className="text-xs text-zinc-500">
              {matrix.company_total} incidents across {matrix.location_count} location
              {matrix.location_count === 1 ? '' : 's'}
            </span>
          )}
        </div>
        <div className="border border-zinc-800 rounded-lg overflow-hidden">
          {matrixLoading ? (
            <div className="p-6 flex items-center justify-center text-zinc-500">
              <Loader2 className="w-4 h-4 animate-spin" />
            </div>
          ) : matrixError ? (
            <p className="p-4 text-sm text-red-400">{matrixError}</p>
          ) : !matrix || matrix.rows.length === 0 ? (
            <p className="p-6 text-sm text-zinc-500 text-center">
              No incidents reported in this window.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-zinc-900 text-zinc-400 text-xs uppercase tracking-wide">
                <tr>
                  <th className="text-left px-4 py-3">Location</th>
                  {TYPE_COLUMNS.map((c) => (
                    <th key={c.key} className="text-right px-4 py-3">{c.label}</th>
                  ))}
                  <th className="text-right px-4 py-3">Total</th>
                </tr>
              </thead>
              <tbody>
                {matrix.rows.map((row) => (
                  <tr key={row.location_id ?? '__unassigned__'} className="border-t border-zinc-900">
                    <td className="px-4 py-3 text-zinc-200">{row.location_name}</td>
                    {TYPE_COLUMNS.map((col) => {
                      const cell = row.cells.find((c) => c.incident_type === col.key)
                      return <MatrixCellView key={col.key} cell={cell} />
                    })}
                    <td className="px-4 py-3 text-right text-zinc-300 font-medium">
                      {row.total_incidents}
                    </td>
                  </tr>
                ))}
                {totalsRow && (
                  <tr className="border-t border-zinc-800 bg-zinc-900/40">
                    <td className="px-4 py-3 text-xs text-zinc-500 uppercase tracking-wide">
                      Company total
                    </td>
                    {TYPE_COLUMNS.map((col) => (
                      <td key={col.key} className="px-4 py-3 text-right text-zinc-400">
                        {totalsRow.totals[col.key] || 0}
                      </td>
                    ))}
                    <td className="px-4 py-3 text-right text-zinc-300 font-medium">
                      {totalsRow.grand}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
        <p className="text-xs text-zinc-500 mt-2">
          <span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1.5" />
          Cell flagged when a location runs ≥2× the company-wide baseline rate for that
          incident type AND has at least 3 incidents.
        </p>
      </section>

      {/* AI Themes */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="flex items-center gap-2 text-xs font-medium text-zinc-400 uppercase tracking-wide">
            <AlertTriangle className="w-3.5 h-3.5" />
            AI Themes · last {insights?.period_days ?? insightDays} days
          </h2>
          {insights && (
            <span className="text-xs text-zinc-500">
              {insights.from_cache ? 'cached' : 'fresh'} · generated {relativeTime(insights.generated_at)}
            </span>
          )}
        </div>
        {insightsLoading ? (
          <div className="border border-zinc-800 rounded-lg p-6 flex items-center justify-center text-zinc-500">
            <Loader2 className="w-4 h-4 animate-spin" />
          </div>
        ) : insightsError ? (
          <p className="text-sm text-red-400">{insightsError}</p>
        ) : !insights || insights.themes.length === 0 ? (
          <div className="border border-zinc-800 rounded-lg p-6 text-sm text-zinc-500 text-center">
            No recurring patterns detected in this window. Themes need ≥3 supporting
            incidents to surface.
          </div>
        ) : (
          <div className="grid gap-3 grid-cols-1 lg:grid-cols-2">
            {insights.themes.map((t, idx) => (
              <ThemeCard
                key={`${t.label}-${idx}`}
                theme={t}
                onNavigateIncident={onNavigateIncident}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function MatrixCellView({ cell }: { cell: IRRiskMatrixCell | undefined }) {
  if (!cell || cell.count === 0) {
    return <td className="px-4 py-3 text-right text-zinc-700">—</td>
  }
  return (
    <td className="px-4 py-3 text-right">
      <span className="inline-flex items-center gap-1.5">
        {cell.flagged && (
          <span
            className="inline-block w-2 h-2 rounded-full bg-red-500"
            title={`${cell.deviation_ratio.toFixed(1)}× company baseline`}
          />
        )}
        <span className={cell.flagged ? 'text-red-300 font-medium' : 'text-zinc-200'}>
          {cell.count}
        </span>
      </span>
    </td>
  )
}

function ThemeCard({
  theme,
  onNavigateIncident,
}: {
  theme: IRRiskTheme
  onNavigateIncident?: (id: string) => void
}) {
  const variant = SEVERITY_BADGE[theme.severity] ?? 'neutral'
  return (
    <div className="border border-zinc-800 rounded-lg p-4 bg-zinc-950 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-sm font-medium text-zinc-100">{theme.label}</h3>
        <Badge variant={variant}>{severityLabel(theme.severity)}</Badge>
      </div>
      <p className="text-xs text-zinc-500">
        {theme.incident_count} incident{theme.incident_count === 1 ? '' : 's'}
        {theme.location_name ? ` at ${theme.location_name}` : ' across multiple locations'}
      </p>
      <p className="text-sm text-zinc-300">{theme.insight}</p>
      <p className="text-xs text-zinc-400">
        <span className="text-zinc-500 uppercase tracking-wide">Suggested:</span>{' '}
        {theme.recommendation}
      </p>
      {theme.evidence_incident_ids.length > 0 && (
        <div className="pt-2 border-t border-zinc-900 flex flex-wrap gap-1.5">
          {theme.evidence_incident_ids.map((id) => (
            <button
              key={id}
              onClick={() => onNavigateIncident?.(id)}
              className="text-[11px] font-mono text-emerald-400 hover:text-emerald-300 underline underline-offset-2"
            >
              {id.slice(0, 8)}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
