import { useState, useMemo } from 'react'
import type { CatCoverage, PolicyDomainSummary } from './types'
import {
  CATEGORY_GROUPS,
  type CategoryGroup,
} from '../../../generated/complianceCategories'

type Props = {
  coverageData: CatCoverage[]
  selectedCategory: string
  onSelectCategory: (cat: string) => void
  policySummary: PolicyDomainSummary[] | null
}

const GROUP_LABELS: Record<CategoryGroup | 'supplementary', string> = {
  labor: 'Labor',
  healthcare: 'Healthcare',
  oncology: 'Oncology',
  medical_compliance: 'Medical Compliance',
  supplementary: 'Supplementary',
}

const GROUP_ORDER: (CategoryGroup | 'supplementary')[] = [
  'labor',
  'healthcare',
  'oncology',
  'medical_compliance',
  'supplementary',
]

export default function CategoryCoveragePanel({
  coverageData,
  selectedCategory,
  onSelectCategory,
  policySummary,
}: Props) {
  const [search, setSearch] = useState('')
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())

  // Build lookup from policy-overview: slug → { requirement_count, jurisdiction_count }
  const policyLookup = useMemo(() => {
    const map: Record<string, { reqCount: number; jurisdictionCount: number }> = {}
    if (!policySummary) return map
    for (const domain of policySummary) {
      for (const cat of domain.categories) {
        map[cat.slug] = { reqCount: cat.requirement_count, jurisdictionCount: cat.jurisdiction_count }
      }
    }
    return map
  }, [policySummary])

  // Domain-level totals from policy summary
  const domainTotals = useMemo(() => {
    const map: Record<string, { catCount: number; reqCount: number }> = {}
    if (!policySummary) return map
    for (const domain of policySummary) {
      map[domain.domain] = { catCount: domain.category_count, reqCount: domain.requirement_count }
    }
    return map
  }, [policySummary])

  // Group coverageData by category group
  const grouped = useMemo(() => {
    const result: Record<string, CatCoverage[]> = {}
    for (const item of coverageData) {
      const group = CATEGORY_GROUPS[item.category] ?? 'supplementary'
      if (!result[group]) result[group] = []
      result[group].push(item)
    }
    return result
  }, [coverageData])

  // Filter by search
  const filteredGrouped = useMemo(() => {
    if (!search) return grouped
    const q = search.toLowerCase()
    const result: Record<string, CatCoverage[]> = {}
    for (const [group, items] of Object.entries(grouped)) {
      const filtered = items.filter(
        (item) =>
          item.label.toLowerCase().includes(q) ||
          item.shortLabel.toLowerCase().includes(q) ||
          item.category.toLowerCase().includes(q)
      )
      if (filtered.length > 0) result[group] = filtered
    }
    return result
  }, [grouped, search])

  function toggleGroup(group: string) {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(group)) next.delete(group)
      else next.add(group)
      return next
    })
  }

  const totalCategories = coverageData.length

  return (
    <div className="w-[260px] shrink-0 border border-zinc-800 rounded-lg overflow-hidden flex flex-col" style={{ maxHeight: 'calc(100vh - 220px)' }}>
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-zinc-800/60">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">
            Categories
          </span>
          <span className="text-[10px] text-zinc-600 font-mono">{totalCategories}</span>
        </div>
        <input
          type="text"
          placeholder="Search categories..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-zinc-900 border border-zinc-700/50 rounded text-xs text-zinc-300 px-2 py-1.5 placeholder-zinc-600 focus:outline-none focus:border-zinc-600"
        />
      </div>

      {/* Scrollable category tree */}
      <div className="overflow-y-auto flex-1">
        {GROUP_ORDER.filter((g) => filteredGrouped[g]?.length).map((group) => {
          const isCollapsed = collapsedGroups.has(group)
          const items = filteredGrouped[group]
          const dt = domainTotals[group]

          return (
            <div key={group}>
              {/* Domain header */}
              <button
                type="button"
                onClick={() => toggleGroup(group)}
                className="w-full flex items-center gap-1.5 px-3 py-2 text-left hover:bg-zinc-800/30 transition-colors border-b border-zinc-800/40"
              >
                <span className="text-zinc-600 text-[10px] w-3">{isCollapsed ? '▸' : '▾'}</span>
                <span className="text-[11px] font-medium text-zinc-300 flex-1">
                  {GROUP_LABELS[group]}
                </span>
                <span className="text-[10px] text-zinc-600 font-mono">
                  {items.length}
                  {dt ? ` · ${dt.reqCount.toLocaleString()}` : ''}
                </span>
              </button>

              {/* Category rows */}
              {!isCollapsed && items.map((item) => {
                const isActive = selectedCategory === item.category
                const policy = policyLookup[item.category]
                const reqCount = policy?.reqCount ?? 0

                return (
                  <button
                    key={item.category}
                    type="button"
                    onClick={() => onSelectCategory(isActive ? '' : item.category)}
                    className={`w-full text-left px-3 py-1.5 pl-7 transition-colors ${
                      isActive
                        ? 'bg-blue-500/10 border-l-2 border-blue-400'
                        : 'hover:bg-zinc-800/30 border-l-2 border-transparent'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className={`text-[11px] flex-1 truncate ${
                        isActive ? 'text-blue-300 font-medium' : 'text-zinc-400'
                      }`}>
                        {item.shortLabel}
                      </span>
                      <span className="text-[10px] text-zinc-600 font-mono shrink-0">
                        {item.count}/{item.total}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      {/* Mini coverage bar */}
                      <div className="flex-1 h-1 rounded-full bg-zinc-800 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            item.pct >= 80
                              ? 'bg-emerald-500'
                              : item.pct >= 50
                                ? 'bg-amber-400'
                                : 'bg-red-400'
                          }`}
                          style={{ width: `${item.pct}%` }}
                        />
                      </div>
                      {reqCount > 0 && (
                        <span className="text-[9px] text-zinc-600 font-mono shrink-0">
                          {reqCount} reqs
                        </span>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          )
        })}

        {Object.keys(filteredGrouped).length === 0 && (
          <div className="px-3 py-6 text-center">
            <p className="text-[11px] text-zinc-600">No categories match</p>
          </div>
        )}
      </div>
    </div>
  )
}
