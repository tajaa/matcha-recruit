import { useState } from 'react'
import type { CatCoverage } from './types'
import {
  CATEGORY_GROUPS,
  type CategoryGroup,
} from '../../../generated/complianceCategories'

type Props = {
  coverageData: CatCoverage[]
  selectedCategory: string
  onSelectCategory: (cat: string) => void
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
}: Props) {
  const [collapsed, setCollapsed] = useState(false)

  // Group coverageData by category group
  const grouped: Record<string, CatCoverage[]> = {}
  for (const item of coverageData) {
    const group = CATEGORY_GROUPS[item.category] ?? 'supplementary'
    if (!grouped[group]) grouped[group] = []
    grouped[group].push(item)
  }

  return (
    <div className="border border-zinc-800 rounded-lg mb-4">
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-zinc-800/30 transition-colors"
      >
        <span className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
          Category Coverage
        </span>
        <span className="text-zinc-600 text-xs">{collapsed ? '▸' : '▾'}</span>
      </button>

      {!collapsed && (
        <div className="px-3 pb-3 space-y-3 border-t border-zinc-800/60">
          {GROUP_ORDER.filter((g) => grouped[g]?.length).map((group) => (
            <div key={group} className="pt-2">
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-1.5">
                {GROUP_LABELS[group]}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {grouped[group].map((item) => {
                  const isActive = selectedCategory === item.category
                  return (
                    <button
                      key={item.category}
                      type="button"
                      onClick={() =>
                        onSelectCategory(
                          isActive ? '' : item.category
                        )
                      }
                      className={`text-[10px] px-2 py-1 rounded transition-colors flex items-center gap-1.5 ${
                        isActive
                          ? 'bg-emerald-500/20 text-emerald-400'
                          : 'text-zinc-400 hover:text-zinc-200 bg-zinc-800/50 hover:bg-zinc-800'
                      }`}
                      title={`${item.label}: ${item.count}/${item.total} cities (${item.pct}%)`}
                    >
                      <span>{item.shortLabel}</span>
                      <span
                        className={`font-mono ${
                          item.pct >= 80
                            ? 'text-emerald-400'
                            : item.pct >= 50
                              ? 'text-amber-400'
                              : 'text-red-400'
                        }`}
                      >
                        {item.pct}%
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
