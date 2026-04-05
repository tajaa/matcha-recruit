import { useMemo } from 'react'
import { MapPin, Building2, Globe } from 'lucide-react'
import type { HeatMapCell } from '../../types/dashboard'

interface Props {
  cells: HeatMapCell[]
}

const SEV_BG: Record<string, string> = {
  critical: 'bg-red-600/50 border-red-700/50 text-red-200',
  high: 'bg-orange-600/40 border-orange-700/40 text-orange-200',
  medium: 'bg-amber-600/30 border-amber-700/30 text-amber-200',
  low: 'bg-blue-600/20 border-blue-700/30 text-blue-200',
  warning: 'bg-orange-600/40 border-orange-700/40 text-orange-200',
}

const SEV_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, warning: 1 }

const GROUP_ICONS: Record<string, typeof MapPin> = {
  Locations: MapPin,
  Departments: Building2,
  'Company-wide': Globe,
}
const GROUP_ORDER = ['Locations', 'Departments', 'Company-wide']

const CAT_ABBR: Record<string, string> = {
  Compliance: 'CMP',
  'Compliance (HR)': 'CMP',
  Safety: 'SAF',
  'HR Policy / Legal': 'HR',
  'Workforce Risk': 'WRK',
}

export function RiskHeatMap({ cells }: Props) {
  const groups = useMemo(() => {
    if (cells.length === 0) return []

    const byGroup = new Map<string, { location: string; cat: string; count: number; severity: string }[]>()
    for (const c of cells) {
      const grp = c.group || 'Locations'
      if (!byGroup.has(grp)) byGroup.set(grp, [])
      byGroup.get(grp)!.push({ location: c.location, cat: c.category, count: c.count, severity: c.worst_severity })
    }

    // Merge cells by location within each group, sort by worst severity then count
    const result: { name: string; items: { location: string; badges: { cat: string; count: number; severity: string }[] }[] }[] = []
    for (const grpName of [...GROUP_ORDER, ...byGroup.keys()]) {
      if (result.some(r => r.name === grpName)) continue
      const entries = byGroup.get(grpName)
      if (!entries) continue

      const locMap = new Map<string, { cat: string; count: number; severity: string }[]>()
      for (const e of entries) {
        if (!locMap.has(e.location)) locMap.set(e.location, [])
        locMap.get(e.location)!.push({ cat: e.cat, count: e.count, severity: e.severity })
      }

      const items = [...locMap.entries()]
        .map(([loc, badges]) => ({
          location: loc,
          badges: badges.sort((a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9)),
          worstSev: Math.min(...badges.map(b => SEV_ORDER[b.severity] ?? 9)),
          totalCount: badges.reduce((s, b) => s + b.count, 0),
        }))
        .sort((a, b) => a.worstSev - b.worstSev || b.totalCount - a.totalCount)
        .slice(0, 6)

      result.push({ name: grpName, items })
    }
    return result
  }, [cells])

  if (groups.length === 0) return null

  return (
    <div className="mb-5">
      <div className="flex items-center gap-4 mb-2.5">
        <h3 className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Risk Concentration</h3>
        <div className="flex items-center gap-3 text-[9px] text-zinc-600">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-red-600/50" />Critical</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-orange-600/40" />High</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-amber-600/30" />Medium</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-blue-600/20" />Low</span>
          <span className="text-zinc-700 mx-1">|</span>
          <span>CMP = Compliance</span>
          <span>SAF = Safety</span>
          <span>HR = HR Policy</span>
          <span>WRK = Workforce</span>
        </div>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-3">
        {groups.map((grp) => {
          const Icon = GROUP_ICONS[grp.name] || MapPin
          return (
            <div key={grp.name} className="flex items-start gap-2">
              <span className="flex items-center gap-1 text-[10px] text-zinc-600 uppercase tracking-wider pt-0.5 shrink-0 w-24">
                <Icon size={9} />
                {grp.name}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {grp.items.map(({ location, badges }) => (
                  <div
                    key={location}
                    className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-900/60 px-2 py-1"
                  >
                    <span className="text-[11px] text-zinc-300 font-medium whitespace-nowrap">{location}</span>
                    {badges.map((b, i) => (
                      <span
                        key={i}
                        className={`inline-flex items-center gap-0.5 px-1.5 py-px rounded text-[9px] font-bold border ${SEV_BG[b.severity] || SEV_BG.medium}`}
                        title={`${b.cat}: ${b.count} flag(s) (${b.severity})`}
                      >
                        {b.count}
                        <span className="font-medium opacity-70">{CAT_ABBR[b.cat] || b.cat.slice(0, 3).toUpperCase()}</span>
                      </span>
                    ))}
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
