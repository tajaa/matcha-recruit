import { useState, useEffect } from 'react'
import { fetchKeyCoverage, runStalenessCheck } from '../../../api/compliance'
import type { CategoryKeyCoverage, RegulationKeyCoverage } from '../../../api/compliance'

interface KeyCoverageDrawerProps {
  jurisdictionId?: string
  category?: string
  state?: string
  onClose: () => void
}

function staleBadge(level: string) {
  switch (level) {
    case 'expired':
      return <span className="px-1.5 py-0.5 text-[10px] font-bold rounded bg-red-500/20 text-red-400 border border-red-500/30">EXPIRED</span>
    case 'critical':
      return <span className="px-1.5 py-0.5 text-[10px] font-bold rounded bg-red-500/20 text-red-400 border border-red-500/30">CRITICAL</span>
    case 'warning':
      return <span className="px-1.5 py-0.5 text-[10px] font-bold rounded bg-yellow-500/20 text-yellow-400 border border-yellow-500/30">STALE</span>
    case 'no_data':
      return <span className="px-1.5 py-0.5 text-[10px] font-bold rounded bg-red-500/30 text-red-300 border border-red-500/40">NO DATA</span>
    default:
      return null
  }
}

function weightBadge(w: number) {
  if (w >= 1.5) return <span className="px-1 py-0.5 text-[10px] rounded bg-purple-500/20 text-purple-300">{w}x</span>
  return null
}

function tierDot(tier: number) {
  if (tier >= 3) return <span className="w-2 h-2 rounded-full bg-green-400 inline-block" title="Tier 1 (Government)" />
  if (tier >= 2) return <span className="w-2 h-2 rounded-full bg-yellow-400 inline-block" title="Tier 2 (Official)" />
  if (tier >= 1) return <span className="w-2 h-2 rounded-full bg-orange-400 inline-block" title="Tier 3 (Aggregator)" />
  return null
}

function KeyRow({ k }: { k: RegulationKeyCoverage }) {
  const isMissing = k.status === 'missing'
  return (
    <div className={`flex items-center gap-2 px-3 py-2 rounded text-sm ${
      isMissing ? 'bg-red-500/10 border border-red-500/20' : 'bg-zinc-800/50'
    }`}>
      <span className={`text-base ${isMissing ? 'text-red-400' : 'text-green-400'}`}>
        {isMissing ? '✕' : '✓'}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={`font-medium truncate ${isMissing ? 'text-red-300' : 'text-zinc-200'}`}>
            {k.name}
          </span>
          {weightBadge(k.base_weight)}
          {staleBadge(k.staleness_level)}
        </div>
        <div className="flex items-center gap-3 mt-0.5 text-xs text-zinc-500">
          <span className="font-mono">{k.key}</span>
          {k.enforcing_agency && <span>{k.enforcing_agency}</span>}
          {k.key_group && <span className="text-zinc-600">group: {k.key_group}</span>}
        </div>
      </div>
      <div className="flex items-center gap-2 text-xs text-zinc-500 shrink-0">
        {!isMissing && (
          <>
            {tierDot(k.best_tier)}
            <span>{k.jurisdiction_count} jur.</span>
            {k.days_since_verified != null && <span>{k.days_since_verified}d ago</span>}
            {k.newest_value && <span className="text-zinc-400 font-mono">{k.newest_value}</span>}
          </>
        )}
      </div>
    </div>
  )
}

function CategorySection({ cat }: { cat: CategoryKeyCoverage }) {
  const [expanded, setExpanded] = useState(cat.coverage_pct < 100)
  const missingCount = cat.expected - cat.present

  return (
    <div className="border border-zinc-700/50 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 bg-zinc-800/50 hover:bg-zinc-800 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-zinc-200">{cat.label}</span>
          <span className="text-xs text-zinc-500">{cat.category}</span>
        </div>
        <div className="flex items-center gap-3">
          {missingCount > 0 && (
            <span className="px-2 py-0.5 text-xs font-bold rounded bg-red-500/20 text-red-400">
              {missingCount} missing
            </span>
          )}
          <div className="flex items-center gap-2">
            <div className="w-24 h-1.5 bg-zinc-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${
                  cat.coverage_pct === 100 ? 'bg-green-500' :
                  cat.coverage_pct >= 50 ? 'bg-yellow-500' : 'bg-red-500'
                }`}
                style={{ width: `${cat.coverage_pct}%` }}
              />
            </div>
            <span className="text-xs font-mono text-zinc-400 w-16 text-right">
              {cat.present}/{cat.expected}
            </span>
          </div>
          <span className="text-zinc-600">{expanded ? '▾' : '▸'}</span>
        </div>
      </button>

      {expanded && (
        <div className="p-2 space-y-1">
          {cat.partial_groups.length > 0 && (
            <div className="px-3 py-2 mb-1 bg-yellow-500/10 border border-yellow-500/20 rounded text-xs text-yellow-400">
              {cat.partial_groups.map(g => (
                <div key={g.group}>
                  <span className="font-medium">{g.group}</span> group: {g.present}/{g.expected} keys
                  {g.present > 0 && g.present < g.expected && ' — partial coverage may be unreliable'}
                </div>
              ))}
            </div>
          )}
          {cat.keys.map(k => <KeyRow key={k.key} k={k} />)}
        </div>
      )}
    </div>
  )
}

export default function KeyCoverageDrawer({ jurisdictionId, category, state, onClose }: KeyCoverageDrawerProps) {
  const [data, setData] = useState<{ summary: any; by_category: CategoryKeyCoverage[] } | null>(null)
  const [loading, setLoading] = useState(true)
  const [runningCheck, setRunningCheck] = useState(false)

  const load = () => {
    setLoading(true)
    fetchKeyCoverage({ jurisdiction_id: jurisdictionId, category, state })
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [jurisdictionId, category, state])

  const handleRunCheck = async () => {
    setRunningCheck(true)
    try {
      const result = await runStalenessCheck({ jurisdiction_id: jurisdictionId, state })
      alert(`Created ${result.alerts_created} alerts, resolved ${result.alerts_resolved}`)
      load()
    } catch {
      // ignore
    } finally {
      setRunningCheck(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative ml-auto w-full max-w-2xl bg-zinc-900 border-l border-zinc-700 shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-700/50">
          <div>
            <h2 className="text-lg font-semibold text-zinc-100">Key Coverage</h2>
            {data && (
              <p className="text-xs text-zinc-500 mt-0.5">
                {data.summary.total_present}/{data.summary.total_defined_keys} keys
                ({data.summary.key_coverage_pct}%)
                {data.summary.stale_warning > 0 && ` · ${data.summary.stale_warning} stale`}
                {data.summary.stale_critical > 0 && ` · ${data.summary.stale_critical} critical`}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRunCheck}
              disabled={runningCheck}
              className="px-3 py-1.5 text-xs font-medium rounded bg-amber-600/20 text-amber-400 border border-amber-600/30 hover:bg-amber-600/30 disabled:opacity-50"
            >
              {runningCheck ? 'Running...' : 'Run Staleness Check'}
            </button>
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 text-xl px-2">&times;</button>
          </div>
        </div>

        {/* Summary bar */}
        {data && (
          <div className="px-5 py-3 border-b border-zinc-700/30 flex items-center gap-4 text-xs">
            <div className="flex items-center gap-2">
              <div className="w-32 h-2 bg-zinc-700 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    data.summary.key_coverage_pct === 100 ? 'bg-green-500' :
                    data.summary.key_coverage_pct >= 50 ? 'bg-yellow-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${Math.min(data.summary.key_coverage_pct, 100)}%` }}
                />
              </div>
              <span className="font-mono text-zinc-400">
                {data.summary.key_coverage_pct}%
              </span>
            </div>
            <span className="text-zinc-500">
              {data.summary.categories_fully_covered} fully covered
            </span>
            <span className="text-zinc-500">
              {data.summary.categories_with_gaps} with gaps
            </span>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {loading ? (
            <div className="text-center py-12 text-zinc-500">Loading...</div>
          ) : data ? (
            data.by_category.map(cat => <CategorySection key={cat.category} cat={cat} />)
          ) : (
            <div className="text-center py-12 text-zinc-500">Failed to load coverage data</div>
          )}
        </div>
      </div>
    </div>
  )
}
