import { useState, useEffect, useMemo } from 'react'
import { fetchQualityAudit } from '../../../api/compliance'
import type { QualityRequirement, QualityAuditResponse } from '../../../api/compliance'
import { CATEGORY_SHORT_LABELS } from '../../../generated/complianceCategories'
import { Button } from '../../ui'

interface RequirementAuditTableProps {
  onEditRequirement?: (requirementId: string) => void
}

type SortKey = 'completeness' | 'staleness' | 'tier'
type SortDir = 'asc' | 'desc'
type SourceFilter = 'All' | 'API' | 'Gemini' | 'Skill' | 'Manual' | 'Unknown'

const PAGE_SIZE = 50

function tierBadge(tier: string) {
  const map: Record<string, string> = {
    'tier_1_government': 'bg-emerald-500/15 text-emerald-400',
    'tier_2_official_secondary': 'bg-blue-500/15 text-blue-400',
    'tier_3_aggregator': 'bg-zinc-500/15 text-zinc-400',
  }
  const tierLabels: Record<string, string> = {
    'tier_1_government': 'T1',
    'tier_2_official_secondary': 'T2',
    'tier_3_aggregator': 'T3',
  }
  const cls = map[tier] ?? 'bg-red-500/15 text-red-400'
  const label = tierLabels[tier] ?? 'None'
  return <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${cls}`}>{label}</span>
}

function provenanceBadge(source: string) {
  const map: Record<string, string> = {
    official_api: 'bg-blue-500/15 text-blue-400',
    gemini: 'bg-violet-500/15 text-violet-400',
    claude_skill: 'bg-amber-500/15 text-amber-400',
    manual: 'bg-slate-500/15 text-slate-400',
  }
  const norm = source?.toLowerCase() ?? ''
  const cls = map[norm] ?? 'bg-red-500/15 text-red-400'
  const labels: Record<string, string> = { official_api: 'API', gemini: 'Gemini', claude_skill: 'Skill', manual: 'Manual' }
  const label = labels[norm] ?? 'Unknown'
  return <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${cls}`}>{label}</span>
}

function stalenessCell(days: number | null) {
  if (days == null) return <span className="text-zinc-600 text-[11px]">—</span>
  const label = days < 1 ? 'today' : `${days}d ago`
  if (days > 90) {
    return <span className="text-amber-400 text-[11px]">⚠ {label}</span>
  }
  return <span className="text-zinc-400 text-[11px]">{label}</span>
}

function qualityFlags(req: QualityRequirement) {
  const flags: string[] = []
  if (!req.description) flags.push('⚠ desc')
  if (!req.source_url) flags.push('🔗')
  if (!req.effective_date) flags.push('📅')
  if (flags.length === 0) return null
  return <span className="text-[10px] text-zinc-500 space-x-1">{flags.join(' ')}</span>
}

export default function RequirementAuditTable({ onEditRequirement }: RequirementAuditTableProps) {
  const [data, setData] = useState<QualityAuditResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [filterState, setFilterState] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterSource, setFilterSource] = useState<SourceFilter>('All')
  const [staleOnly, setStaleOnly] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('completeness')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [page, setPage] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchQualityAudit({ limit: 2000 })
      .then((d) => { if (!cancelled) setData(d) })
      .catch((e) => { if (!cancelled) setError(e?.message ?? 'Failed to load') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const allStates = useMemo(() => {
    if (!data) return []
    return [...new Set(data.requirements.map((r) => r.state))].sort()
  }, [data])

  const allCategories = useMemo(() => {
    if (!data) return []
    return [...new Set(data.requirements.map((r) => r.category))].sort()
  }, [data])

  const filtered = useMemo(() => {
    if (!data) return []
    let rows = data.requirements
    if (filterState) rows = rows.filter((r) => r.state === filterState)
    if (filterCategory) rows = rows.filter((r) => r.category === filterCategory)
    if (staleOnly) rows = rows.filter((r) => r.staleness_days != null && r.staleness_days > 90)
    if (filterSource !== 'All') {
      const sourceMap: Record<string, string> = {
        API: 'official_api',
        Gemini: 'gemini',
        Skill: 'claude_skill',
        Manual: 'manual',
      }
      rows = rows.filter((r) => {
        const rs = r.research_source?.toLowerCase() ?? ''
        if (filterSource === 'Unknown') return !rs || !['official_api', 'gemini', 'claude_skill', 'manual'].includes(rs)
        return rs === sourceMap[filterSource]
      })
    }
    return rows
  }, [data, filterState, filterCategory, staleOnly, filterSource])

  const sorted = useMemo(() => {
    const arr = [...filtered]
    const dir = sortDir === 'asc' ? 1 : -1
    arr.sort((a, b) => {
      if (sortKey === 'completeness') return dir * (a.completeness_score - b.completeness_score)
      if (sortKey === 'staleness') {
        const da = a.staleness_days ?? -1
        const db = b.staleness_days ?? -1
        return dir * (da - db)
      }
      if (sortKey === 'tier') return dir * ((a.source_tier ?? '9').localeCompare(b.source_tier ?? '9'))
      return 0
    })
    return arr
  }, [filtered, sortKey, sortDir])

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE)
  const paged = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('asc') }
    setPage(0)
  }

  function sortIcon(key: SortKey) {
    if (sortKey !== key) return ''
    return sortDir === 'asc' ? ' ↑' : ' ↓'
  }

  if (loading) {
    return (
      <div className="space-y-2 animate-pulse">
        <div className="h-8 bg-zinc-800 rounded w-full" />
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

  return (
    <div className="space-y-3">
      {/* Summary bar */}
      <div className="flex flex-wrap items-center gap-4 text-[11px] text-zinc-500 border border-zinc-800 rounded-lg px-3 py-2">
        <span>Total: <span className="text-zinc-300 font-mono">{data.summary.total}</span></span>
        <span>Avg completeness: <span className="text-zinc-300 font-mono">{Math.round(data.summary.avg_completeness)}%</span></span>
        <span>Stale: <span className={`font-mono ${data.summary.stale_count > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>{data.summary.stale_count}</span></span>
        <span>Missing URL: <span className={`font-mono ${data.summary.missing_source_url > 0 ? 'text-red-400' : 'text-emerald-400'}`}>{data.summary.missing_source_url}</span></span>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={filterState}
          onChange={(e) => { setFilterState(e.target.value); setPage(0) }}
          className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5"
        >
          <option value="">All States</option>
          {allStates.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select
          value={filterCategory}
          onChange={(e) => { setFilterCategory(e.target.value); setPage(0) }}
          className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5"
        >
          <option value="">All Categories</option>
          {allCategories.map((c) => (
            <option key={c} value={c}>{CATEGORY_SHORT_LABELS[c] ?? c}</option>
          ))}
        </select>
        <select
          value={filterSource}
          onChange={(e) => { setFilterSource(e.target.value as SourceFilter); setPage(0) }}
          className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5"
        >
          {(['All', 'API', 'Gemini', 'Skill', 'Manual', 'Unknown'] as SourceFilter[]).map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => { setStaleOnly(!staleOnly); setPage(0) }}
          className={`text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${
            staleOnly
              ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
              : 'border-zinc-700 text-zinc-500 hover:text-zinc-300'
          }`}
        >
          Stale only
        </button>
        <span className="text-[11px] text-zinc-600 ml-auto">{sorted.length} requirements</span>
      </div>

      {/* Table */}
      <div className="border border-zinc-800 rounded-lg overflow-hidden">
        {sorted.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-sm text-zinc-600">No requirements match these filters.</p>
          </div>
        ) : (
          <>
            <div className="max-h-[55vh] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="bg-zinc-900/50 text-zinc-400 sticky top-0">
                  <tr>
                    <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide whitespace-nowrap">Jurisdiction</th>
                    <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Category</th>
                    <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Title</th>
                    <th
                      className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide cursor-pointer hover:text-zinc-200 select-none whitespace-nowrap"
                      onClick={() => toggleSort('completeness')}
                    >
                      Complete{sortIcon('completeness')}
                    </th>
                    <th
                      className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide cursor-pointer hover:text-zinc-200 select-none"
                      onClick={() => toggleSort('tier')}
                    >
                      Tier{sortIcon('tier')}
                    </th>
                    <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Source</th>
                    <th
                      className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide cursor-pointer hover:text-zinc-200 select-none"
                      onClick={() => toggleSort('staleness')}
                    >
                      Stale{sortIcon('staleness')}
                    </th>
                    <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Flags</th>
                    <th className="py-2 px-3 w-14" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {paged.map((req) => (
                    <tr key={req.id} className="hover:bg-zinc-800/30">
                      <td className="py-1.5 px-3 whitespace-nowrap">
                        <span className="font-mono font-bold text-zinc-200 text-[11px]">{req.state}</span>
                        {req.city && <span className="text-zinc-500 text-[11px] ml-1">{req.city}</span>}
                      </td>
                      <td className="py-1.5 px-3 text-zinc-400 text-[11px] whitespace-nowrap">
                        {CATEGORY_SHORT_LABELS[req.category] ?? req.category}
                      </td>
                      <td className="py-1.5 px-3 text-zinc-300 text-[11px] max-w-[180px]" title={req.title ?? undefined}>
                        {(req.title?.length ?? 0) > 40 ? req.title!.slice(0, 40) + '…' : req.title}
                      </td>
                      <td className="py-1.5 px-3">
                        <div className="flex items-center gap-1.5">
                          <div className="w-12 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                req.completeness_score >= 70 ? 'bg-emerald-500' :
                                req.completeness_score >= 40 ? 'bg-amber-400' : 'bg-red-400'
                              }`}
                              style={{ width: `${req.completeness_score}%` }}
                            />
                          </div>
                          <span className="text-[10px] font-mono text-zinc-500">{Math.round(req.completeness_score)}%</span>
                        </div>
                      </td>
                      <td className="py-1.5 px-3">{tierBadge(req.source_tier ?? '')}</td>
                      <td className="py-1.5 px-3">{provenanceBadge(req.research_source ?? '')}</td>
                      <td className="py-1.5 px-3">{stalenessCell(req.staleness_days)}</td>
                      <td className="py-1.5 px-3">{qualityFlags(req)}</td>
                      <td className="py-1.5 px-3">
                        <button
                          type="button"
                          onClick={() => onEditRequirement?.(req.id)}
                          className="text-[10px] text-zinc-600 hover:text-zinc-300 transition-colors px-1.5 py-0.5 rounded hover:bg-zinc-800"
                        >
                          Edit
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-3 py-2 border-t border-zinc-800/60">
                <span className="text-[11px] text-zinc-600">
                  Page {page + 1} of {totalPages} ({sorted.length} total)
                </span>
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                    Prev
                  </Button>
                  <Button variant="ghost" size="sm" disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)}>
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
