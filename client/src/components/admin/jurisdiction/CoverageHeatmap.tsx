import { useState, useEffect, useMemo } from 'react'
import { fetchCoverageMatrix } from '../../../api/compliance'
import type { CoverageMatrixResponse, CoverageCell } from '../../../api/compliance'
import {
  CATEGORY_SHORT_LABELS,
  HEALTHCARE_CATEGORIES,
  ONCOLOGY_CATEGORIES,
  MEDICAL_COMPLIANCE_CATEGORIES,
  LABOR_CATEGORIES,
  SUPPLEMENTARY_CATEGORIES,
} from '../../../generated/complianceCategories'

interface CoverageHeatmapProps {
  onCellClick?: (jurisdictionId: string, category: string) => void
}

type DomainFilter = 'All' | 'Healthcare' | 'HR'

// Healthcare = clinical + oncology + medical compliance (all non-labor categories)
const HEALTHCARE_CATS = new Set([
  ...HEALTHCARE_CATEGORIES,
  ...ONCOLOGY_CATEGORIES,
  ...MEDICAL_COMPLIANCE_CATEGORIES,
])

// HR = labor + supplementary (posting, licenses, taxes)
const HR_CATS = new Set([
  ...LABOR_CATEGORIES,
  ...SUPPLEMENTARY_CATEGORIES,
])

function cellColor(cell: CoverageCell | undefined): string {
  if (!cell || cell.req_count === 0) return 'bg-zinc-800 text-zinc-600'
  if (cell.best_tier >= 2 || cell.avg_completeness > 70) return 'bg-green-900/60 text-green-400'
  if (cell.best_tier <= 1 && cell.avg_completeness < 40) return 'bg-red-900/60 text-red-400'
  return 'bg-yellow-900/60 text-yellow-400'
}

function tierLabel(tier: number): string {
  if (tier <= 0) return 'None'
  return `T${tier}`
}

function stalenessText(days: number | null): string {
  if (days == null) return 'Unknown'
  if (days <= 90) return `${days}d`
  return `${days}d (stale)`
}

export default function CoverageHeatmap({ onCellClick }: CoverageHeatmapProps) {
  const [data, setData] = useState<CoverageMatrixResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filterState, setFilterState] = useState('')
  const [domainFilter, setDomainFilter] = useState<DomainFilter>('All')
  const [gapsOnly, setGapsOnly] = useState(false)
  const [tooltip, setTooltip] = useState<{
    jId: string; cat: string; cell: CoverageCell | undefined
    jName: string; x: number; y: number
  } | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchCoverageMatrix({})
      .then((d) => { if (!cancelled) setData(d) })
      .catch((e) => { if (!cancelled) setError(e?.message ?? 'Failed to load') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const allStates = useMemo(() => {
    if (!data) return []
    return [...new Set(data.jurisdictions.map((j) => j.state))].sort()
  }, [data])

  const filteredJurisdictions = useMemo(() => {
    if (!data) return []
    let list = data.jurisdictions
    if (filterState) list = list.filter((j) => j.state === filterState)
    return list
  }, [data, filterState])

  const filteredCategories = useMemo(() => {
    if (!data) return []
    return data.categories.filter((cat) => {
      if (domainFilter === 'Healthcare') return HEALTHCARE_CATS.has(cat)
      if (domainFilter === 'HR') return HR_CATS.has(cat)
      return true
    })
  }, [data, domainFilter])

  const displayJurisdictions = useMemo(() => {
    if (!gapsOnly || !data) return filteredJurisdictions
    return filteredJurisdictions.filter((j) =>
      filteredCategories.some((cat) => {
        const key = `${j.id}:${cat}`
        const cell = data.cells[key]
        return !cell || cell.req_count === 0
      })
    )
  }, [filteredJurisdictions, filteredCategories, gapsOnly, data])

  if (loading) {
    return (
      <div className="space-y-2 animate-pulse">
        <div className="h-8 bg-zinc-800 rounded w-64" />
        <div className="h-64 bg-zinc-800 rounded" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
        <p className="text-sm text-zinc-600">{error ?? 'No data available'}</p>
      </div>
    )
  }

  const hasData = displayJurisdictions.length > 0 && filteredCategories.length > 0

  return (
    <div className="space-y-3">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={filterState}
          onChange={(e) => setFilterState(e.target.value)}
          className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5"
        >
          <option value="">All States</option>
          {allStates.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <div className="flex rounded-lg overflow-hidden border border-zinc-700 text-xs">
          {(['All', 'Healthcare', 'HR'] as DomainFilter[]).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDomainFilter(d)}
              className={`px-2.5 py-1.5 transition-colors ${
                domainFilter === d
                  ? 'bg-zinc-700 text-zinc-100'
                  : 'bg-zinc-900 text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {d}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setGapsOnly(!gapsOnly)}
          className={`text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${
            gapsOnly
              ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
              : 'border-zinc-700 text-zinc-500 hover:text-zinc-300'
          }`}
        >
          Show gaps only
        </button>
        <span className="text-[11px] text-zinc-600 ml-auto">
          {displayJurisdictions.length} jurisdictions · {filteredCategories.length} categories
        </span>
      </div>

      {!hasData ? (
        <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
          <p className="text-sm text-zinc-600">No data matches these filters.</p>
        </div>
      ) : (<>
      {/* Heatmap grid */}
      <div className="border border-zinc-800 rounded-lg overflow-auto max-h-[60vh]">
        <table className="text-xs border-collapse">
          <thead className="sticky top-0 z-10 bg-zinc-950">
            <tr>
              <th className="py-1.5 px-2 text-left text-[10px] text-zinc-500 uppercase tracking-wide whitespace-nowrap min-w-[120px] bg-zinc-950">
                Jurisdiction
              </th>
              {filteredCategories.map((cat) => (
                <th
                  key={cat}
                  className="py-1.5 px-1 text-center text-[9px] text-zinc-500 uppercase tracking-wide whitespace-nowrap bg-zinc-950"
                  style={{ minWidth: 36 }}
                  title={cat}
                >
                  {CATEGORY_SHORT_LABELS[cat] ?? cat.slice(0, 8)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayJurisdictions.map((j) => (
              <tr key={j.id} className="hover:bg-zinc-900/40">
                <td className="py-0.5 px-2 text-zinc-300 whitespace-nowrap font-mono text-[11px] sticky left-0 bg-zinc-950 z-[5]">
                  {j.city || j.name}, {j.state}
                </td>
                {filteredCategories.map((cat) => {
                  const key = `${j.id}:${cat}`
                  const cell = data.cells[key]
                  const color = cellColor(cell)
                  return (
                    <td key={cat} className="py-0.5 px-0.5 text-center">
                      <div
                        className={`w-7 h-5 mx-auto rounded-sm cursor-pointer transition-opacity hover:opacity-80 flex items-center justify-center text-[9px] font-mono ${color}`}
                        onClick={() => onCellClick?.(j.id, cat)}
                        onMouseEnter={(e) => {
                          const rect = (e.target as HTMLElement).getBoundingClientRect()
                          setTooltip({ jId: j.id, cat, cell, jName: j.city || j.name, x: rect.left, y: rect.top })
                        }}
                        onMouseLeave={() => setTooltip(null)}
                      >
                        {cell && cell.req_count > 0 ? cell.req_count : ''}
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-[11px] text-zinc-500">
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-green-900/60 inline-block" /> Good (T2+ or &gt;70%)</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-yellow-900/60 inline-block" /> Fair</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-red-900/60 inline-block" /> Poor (T1, &lt;40%)</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-zinc-800 inline-block" /> No data</span>
      </div>

      {/* Floating tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 pointer-events-none bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-[11px] text-zinc-200 shadow-xl max-w-[200px]"
          style={{ left: tooltip.x + 8, top: Math.max(8, tooltip.y - 80) }}
        >
          <p className="font-medium text-zinc-100">{tooltip.jName}</p>
          <p className="text-zinc-400">{CATEGORY_SHORT_LABELS[tooltip.cat] ?? tooltip.cat}</p>
          {tooltip.cell && tooltip.cell.req_count > 0 ? (
            <>
              <p>Reqs: <span className="font-mono text-zinc-200">{tooltip.cell.req_count}</span></p>
              <p>Best tier: <span className="font-mono text-zinc-200">{tierLabel(tooltip.cell.best_tier)}</span></p>
              <p>Completeness: <span className="font-mono text-zinc-200">{Math.round(tooltip.cell.avg_completeness)}%</span></p>
              {tooltip.cell.max_staleness_days != null && (
                <p>Staleness: <span className={`font-mono ${tooltip.cell.max_staleness_days > 90 ? 'text-amber-400' : 'text-zinc-200'}`}>{stalenessText(tooltip.cell.max_staleness_days)}</span></p>
              )}
            </>
          ) : (
            <p className="text-zinc-500">No data</p>
          )}
        </div>
      )}
      </>)}
    </div>
  )
}
