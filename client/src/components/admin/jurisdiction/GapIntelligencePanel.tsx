import { useState, useEffect, useMemo } from 'react'
import { fetchCoverageMatrix } from '../../../api/compliance'
import type { CoverageMatrixResponse, CoverageCell } from '../../../api/compliance'
import { CATEGORY_SHORT_LABELS } from '../../../generated/complianceCategories'

interface Gap {
  jurisdictionId: string
  jurisdictionName: string
  state: string
  category: string
  cell: CoverageCell | null
  priority: number
  description: string
}

function computeGaps(data: CoverageMatrixResponse): Gap[] {
  const gaps: Gap[] = []
  for (const j of data.jurisdictions) {
    for (const cat of data.categories) {
      const key = `${j.id}:${cat}`
      const cell = data.cells[key] ?? null
      const reqCount = cell?.req_count ?? 0
      const bestTier = cell?.best_tier ?? 0
      const staleness = cell?.max_staleness_days ?? null
      const completeness = cell?.avg_completeness ?? 0

      // Only surface gaps
      const hasIssue =
        reqCount === 0 ||
        bestTier <= 1 ||
        (staleness != null && staleness > 90) ||
        completeness < 40

      if (!hasIssue) continue

      const priority =
        (reqCount === 0 ? 100 : 0) +
        (reqCount > 0 && bestTier <= 1 ? 30 : 0) +
        (staleness != null && staleness > 90 ? 20 : 0) +
        (reqCount > 0 && completeness < 40 ? 15 : 0)

      let description = 'No data'
      if (reqCount > 0) {
        const parts: string[] = []
        if (staleness != null && staleness > 90) parts.push(`${staleness}d stale`)
        if (completeness < 40) parts.push(`Low quality (${Math.round(completeness)}%)`)
        if (bestTier <= 1) parts.push('T1 only')
        description = parts.length > 0 ? parts.join(', ') : `${reqCount} reqs`
      }

      gaps.push({
        jurisdictionId: j.id,
        jurisdictionName: j.city || j.name,
        state: j.state,
        category: cat,
        cell,
        priority,
        description,
      })
    }
  }

  gaps.sort((a, b) => b.priority - a.priority)
  return gaps.slice(0, 100) // compute top 100 before filtering
}

function priorityColor(score: number): string {
  if (score >= 100) return 'bg-red-500/15 text-red-400'
  if (score >= 50) return 'bg-amber-500/15 text-amber-400'
  return 'bg-zinc-500/15 text-zinc-400'
}

export default function GapIntelligencePanel() {
  const [data, setData] = useState<CoverageMatrixResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filterState, setFilterState] = useState('')

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

  const gaps = useMemo(() => {
    if (!data) return []
    return computeGaps(data)
  }, [data])

  const filteredGaps = useMemo(() => {
    let list = gaps
    if (filterState) list = list.filter((g) => g.state === filterState)
    return list.slice(0, 20)
  }, [gaps, filterState])

  if (loading) {
    return (
      <div className="space-y-2 animate-pulse">
        <div className="h-8 bg-zinc-800 rounded w-48" />
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-16 bg-zinc-800 rounded" />
        ))}
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

  return (
    <div className="space-y-3">
      {/* Filter bar */}
      <div className="flex items-center gap-2">
        <select
          value={filterState}
          onChange={(e) => setFilterState(e.target.value)}
          className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5"
        >
          <option value="">All States</option>
          {allStates.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <span className="text-[11px] text-zinc-600 ml-auto">
          {filteredGaps.length} of {gaps.length} gaps shown
        </span>
      </div>

      {filteredGaps.length === 0 ? (
        <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
          <p className="text-sm text-zinc-600">No critical gaps found.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredGaps.map((gap) => (
            <div
              key={`${gap.jurisdictionId}:${gap.category}`}
              className="border border-zinc-800 rounded-lg px-3 py-3 flex items-start justify-between gap-3 hover:bg-zinc-800/20 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-zinc-200 text-sm font-medium">
                    {gap.jurisdictionName}, {gap.state}
                  </span>
                  <span className="text-[11px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">
                    {CATEGORY_SHORT_LABELS[gap.category] ?? gap.category}
                  </span>
                </div>
                <p className="text-[11px] text-zinc-500 mt-0.5">{gap.description}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${priorityColor(gap.priority)}`}>
                  P{gap.priority}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    // TODO: wire up to AI research workflow
                    console.log('[GapIntelligencePanel] Research Now clicked:', { jurisdictionId: gap.jurisdictionId, category: gap.category })
                  }}
                  className="text-[11px] px-2 py-1 rounded border border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-500 transition-colors"
                >
                  Research Now
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
