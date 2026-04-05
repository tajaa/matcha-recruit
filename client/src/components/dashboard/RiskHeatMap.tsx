import { useMemo } from 'react'
import type { DashboardFlag } from '../../types/dashboard'

interface Props {
  flags: DashboardFlag[]
}

const SEV_RANK: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 }

const CELL_STYLES: Record<string, string> = {
  critical: 'bg-red-600/40 text-red-300 border-red-700/40',
  high: 'bg-orange-600/30 text-orange-300 border-orange-700/30',
  medium: 'bg-amber-600/20 text-amber-300 border-amber-700/20',
  low: 'bg-blue-600/15 text-blue-300 border-blue-700/20',
  empty: 'bg-zinc-900/50 text-zinc-700 border-zinc-800/30',
}

export function RiskHeatMap({ flags }: Props) {
  const { locations, categories, grid } = useMemo(() => {
    if (flags.length === 0) return { locations: [], categories: [], grid: new Map() }

    const locSet = new Set<string>()
    const catSet = new Set<string>()
    const cells = new Map<string, { count: number; worstSev: string }>()

    for (const f of flags) {
      const loc = f.location_subject || 'Other'
      const cat = f.category || 'Other'
      locSet.add(loc)
      catSet.add(cat)

      const key = `${loc}||${cat}`
      const existing = cells.get(key)
      if (existing) {
        existing.count++
        if ((SEV_RANK[f.severity] ?? 99) < (SEV_RANK[existing.worstSev] ?? 99)) {
          existing.worstSev = f.severity
        }
      } else {
        cells.set(key, { count: 1, worstSev: f.severity })
      }
    }

    // Sort locations by total flag count descending
    const locArr = [...locSet].sort((a, b) => {
      const aCount = [...cells.entries()].filter(([k]) => k.startsWith(`${a}||`)).reduce((s, [, v]) => s + v.count, 0)
      const bCount = [...cells.entries()].filter(([k]) => k.startsWith(`${b}||`)).reduce((s, [, v]) => s + v.count, 0)
      return bCount - aCount
    })

    // Stable category order
    const catOrder = ['Compliance', 'Compliance (HR)', 'Safety', 'HR Policy / Legal', 'Workforce Risk']
    const catArr = catOrder.filter(c => catSet.has(c))
    for (const c of catSet) {
      if (!catArr.includes(c)) catArr.push(c)
    }

    return { locations: locArr, categories: catArr, grid: cells }
  }, [flags])

  // Don't render if fewer than 2 locations or no flags
  if (locations.length < 2 || categories.length === 0) return null

  return (
    <div className="mb-6">
      <h3 className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-3">Risk Concentration</h3>
      <div className="rounded-xl border border-zinc-800 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-zinc-800/50">
              <th className="text-left px-3 py-2 text-zinc-500 font-medium w-40" />
              {categories.map((cat) => (
                <th key={cat} className="text-center px-3 py-2 text-zinc-500 font-medium whitespace-nowrap">
                  {cat}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {locations.slice(0, 8).map((loc) => (
              <tr key={loc} className="border-b border-zinc-800/30">
                <td className="px-3 py-2 text-zinc-300 font-medium truncate max-w-[160px]" title={loc}>
                  {loc}
                </td>
                {categories.map((cat) => {
                  const cell = grid.get(`${loc}||${cat}`)
                  const style = cell ? CELL_STYLES[cell.worstSev] || CELL_STYLES.low : CELL_STYLES.empty
                  return (
                    <td key={cat} className="px-3 py-2 text-center">
                      <span
                        className={`inline-flex items-center justify-center w-8 h-8 rounded-lg border text-[11px] font-semibold ${style}`}
                        title={cell ? `${cell.count} flag(s), worst: ${cell.worstSev}` : 'No flags'}
                      >
                        {cell ? cell.count : '--'}
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {locations.length > 8 && (
        <p className="text-[10px] text-zinc-600 mt-1 px-1">Showing top 8 of {locations.length} locations</p>
      )}
    </div>
  )
}
