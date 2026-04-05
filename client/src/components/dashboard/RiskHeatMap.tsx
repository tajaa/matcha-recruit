import { useMemo } from 'react'
import { MapPin, Building2, Globe } from 'lucide-react'
import type { HeatMapCell } from '../../types/dashboard'

interface Props {
  cells: HeatMapCell[]
}

const CELL_STYLES: Record<string, string> = {
  critical: 'bg-red-600/40 text-red-300 border-red-700/40',
  high: 'bg-orange-600/30 text-orange-300 border-orange-700/30',
  medium: 'bg-amber-600/20 text-amber-300 border-amber-700/20',
  low: 'bg-blue-600/15 text-blue-300 border-blue-700/20',
  warning: 'bg-orange-600/30 text-orange-300 border-orange-700/30',
  empty: 'bg-zinc-900/50 text-zinc-700 border-zinc-800/30',
}

const GROUP_ORDER = ['Locations', 'Departments', 'Company-wide']
const GROUP_ICONS: Record<string, typeof MapPin> = {
  Locations: MapPin,
  Departments: Building2,
  'Company-wide': Globe,
}

export function RiskHeatMap({ cells }: Props) {
  const { groups, categories, grid } = useMemo(() => {
    if (cells.length === 0) return { groups: [], categories: [], grid: new Map<string, HeatMapCell>() }

    const catSet = new Set<string>()
    const gridMap = new Map<string, HeatMapCell>()
    const groupLocs = new Map<string, Map<string, number>>() // group -> (location -> total count)

    for (const c of cells) {
      const grp = c.group || 'Locations'
      catSet.add(c.category)
      gridMap.set(`${c.location}||${c.category}`, c)

      if (!groupLocs.has(grp)) groupLocs.set(grp, new Map())
      const locMap = groupLocs.get(grp)!
      locMap.set(c.location, (locMap.get(c.location) || 0) + c.count)
    }

    // Sort categories in stable order
    const catOrder = ['Compliance', 'Safety', 'HR Policy / Legal', 'Workforce Risk']
    const catArr = catOrder.filter(c => catSet.has(c))
    for (const c of catSet) {
      if (!catArr.includes(c)) catArr.push(c)
    }

    // Build ordered groups with sorted locations
    const orderedGroups: { name: string; locations: string[] }[] = []
    for (const grpName of GROUP_ORDER) {
      const locMap = groupLocs.get(grpName)
      if (!locMap || locMap.size === 0) continue
      const sortedLocs = [...locMap.entries()]
        .sort((a, b) => b[1] - a[1])
        .map(([loc]) => loc)
        .slice(0, 6)
      orderedGroups.push({ name: grpName, locations: sortedLocs })
    }
    // Any groups not in GROUP_ORDER
    for (const [grpName, locMap] of groupLocs) {
      if (GROUP_ORDER.includes(grpName)) continue
      const sortedLocs = [...locMap.entries()]
        .sort((a, b) => b[1] - a[1])
        .map(([loc]) => loc)
        .slice(0, 6)
      orderedGroups.push({ name: grpName, locations: sortedLocs })
    }

    return { groups: orderedGroups, categories: catArr, grid: gridMap }
  }, [cells])

  if (groups.length === 0 || categories.length === 0) return null

  return (
    <div className="mb-6">
      <h3 className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-3">Risk Concentration</h3>
      <div className="rounded-xl border border-zinc-800 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-zinc-800/50">
              <th className="text-left px-3 py-2 text-zinc-500 font-medium w-44" />
              {categories.map((cat) => (
                <th key={cat} className="text-center px-3 py-2 text-zinc-500 font-medium whitespace-nowrap">
                  {cat}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map((grp) => {
              const Icon = GROUP_ICONS[grp.name] || MapPin
              return (
                <>{/* Group section */}
                  <tr key={`hdr-${grp.name}`}>
                    <td
                      colSpan={categories.length + 1}
                      className="px-3 pt-3 pb-1"
                    >
                      <span className="flex items-center gap-1.5 text-[10px] font-medium text-zinc-500 uppercase tracking-wider">
                        <Icon size={10} />
                        {grp.name}
                      </span>
                    </td>
                  </tr>
                  {grp.locations.map((loc) => (
                    <tr key={`${grp.name}-${loc}`} className="border-b border-zinc-800/20">
                      <td className="px-3 py-2 text-zinc-300 font-medium truncate max-w-[180px] pl-6" title={loc}>
                        {loc}
                      </td>
                      {categories.map((cat) => {
                        const cell = grid.get(`${loc}||${cat}`)
                        const style = cell ? CELL_STYLES[cell.worst_severity] || CELL_STYLES.low : CELL_STYLES.empty
                        return (
                          <td key={cat} className="px-3 py-1.5 text-center">
                            <span
                              className={`inline-flex items-center justify-center w-8 h-8 rounded-lg border text-[11px] font-semibold ${style}`}
                              title={cell ? `${cell.count} flag(s), worst: ${cell.worst_severity}` : 'No flags'}
                            >
                              {cell ? cell.count : '--'}
                            </span>
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
