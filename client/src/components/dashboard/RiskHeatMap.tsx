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
}

const GROUP_ORDER = ['Locations', 'Departments', 'Company-wide']
const GROUP_ICONS: Record<string, typeof MapPin> = {
  Locations: MapPin,
  Departments: Building2,
  'Company-wide': Globe,
}

export function RiskHeatMap({ cells }: Props) {
  const groups = useMemo(() => {
    if (cells.length === 0) return []

    // Group cells by group name, then by location
    const byGroup = new Map<string, Map<string, HeatMapCell[]>>()
    for (const c of cells) {
      const grp = c.group || 'Locations'
      if (!byGroup.has(grp)) byGroup.set(grp, new Map())
      const locMap = byGroup.get(grp)!
      if (!locMap.has(c.location)) locMap.set(c.location, [])
      locMap.get(c.location)!.push(c)
    }

    // Build compact card data per group
    const result: { name: string; items: { location: string; cells: HeatMapCell[] }[] }[] = []
    for (const grpName of GROUP_ORDER) {
      const locMap = byGroup.get(grpName)
      if (!locMap || locMap.size === 0) continue
      const items = [...locMap.entries()]
        .map(([loc, locCells]) => ({ location: loc, cells: locCells, total: locCells.reduce((s, c) => s + c.count, 0) }))
        .sort((a, b) => b.total - a.total)
        .slice(0, 5)
      result.push({ name: grpName, items })
    }
    // Any non-standard groups
    for (const [grpName, locMap] of byGroup) {
      if (GROUP_ORDER.includes(grpName)) continue
      const items = [...locMap.entries()]
        .map(([loc, locCells]) => ({ location: loc, cells: locCells, total: locCells.reduce((s, c) => s + c.count, 0) }))
        .sort((a, b) => b.total - a.total)
        .slice(0, 5)
      result.push({ name: grpName, items })
    }
    return result
  }, [cells])

  if (groups.length === 0) return null

  return (
    <div className="mb-6">
      <h3 className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-3">Risk Concentration</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {groups.map((grp) => {
          const Icon = GROUP_ICONS[grp.name] || MapPin
          return (
            <div key={grp.name} className="rounded-xl border border-zinc-800 bg-zinc-900/30 overflow-hidden">
              <div className="px-3 py-2 border-b border-zinc-800/50">
                <span className="flex items-center gap-1.5 text-[10px] font-medium text-zinc-500 uppercase tracking-wider">
                  <Icon size={10} />
                  {grp.name}
                </span>
              </div>
              <div className="divide-y divide-zinc-800/30">
                {grp.items.map(({ location, cells: locCells }) => (
                  <div key={location} className="flex items-center gap-2 px-3 py-2">
                    <span className="text-xs text-zinc-300 font-medium truncate flex-1 min-w-0" title={location}>
                      {location}
                    </span>
                    <div className="flex gap-1.5 shrink-0">
                      {locCells.map((c, i) => {
                        const style = CELL_STYLES[c.worst_severity] || CELL_STYLES.medium
                        return (
                          <span
                            key={i}
                            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-semibold ${style}`}
                            title={`${c.category}: ${c.count} flag(s), ${c.worst_severity}`}
                          >
                            {c.count}
                            <span className="font-normal text-[9px] opacity-70">
                              {c.category === 'Compliance' ? 'CMP'
                                : c.category === 'Safety' ? 'SAF'
                                : c.category === 'HR Policy / Legal' ? 'HR'
                                : c.category === 'Workforce Risk' ? 'WRK'
                                : c.category.slice(0, 3).toUpperCase()}
                            </span>
                          </span>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
