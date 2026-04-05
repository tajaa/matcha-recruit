import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, ChevronUp, ChevronDown, AlertTriangle, RefreshCw, Loader2 } from 'lucide-react'
import type { DashboardFlag, HeatMapCell } from '../../types/dashboard'
import { RiskHeatMap } from './RiskHeatMap'

interface Props {
  flags: DashboardFlag[]
  heatMap: HeatMapCell[]
  totalFlags: number
  criticalCount: number
  analyzedAt: string | null
  onRefresh?: () => void
  refreshing?: boolean
}

type SortKey = 'priority' | 'category' | 'location_subject'
type SortDir = 'asc' | 'desc'

function timeAgo(iso: string): string {
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  return `${hrs}h ago`
}

export function FlagsTable({ flags, heatMap, totalFlags, criticalCount, analyzedAt, onRefresh, refreshing }: Props) {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [priorityFilter, setPriorityFilter] = useState<string>('all')
  const [sortKey, setSortKey] = useState<SortKey>('priority')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const filtered = flags
    .filter((f) => {
      if (priorityFilter === 'critical') return f.severity === 'critical'
      if (priorityFilter === 'high') return f.severity === 'high' || f.severity === 'critical'
      if (priorityFilter === 'medium') return f.severity === 'medium'
      if (priorityFilter === 'low') return f.severity === 'low'
      return true
    })
    .filter((f) => {
      if (!search) return true
      const q = search.toLowerCase()
      return (
        f.description.toLowerCase().includes(q) ||
        f.category.toLowerCase().includes(q) ||
        f.location_subject.toLowerCase().includes(q) ||
        f.recommendation.toLowerCase().includes(q)
      )
    })
    .sort((a, b) => {
      let cmp = 0
      if (sortKey === 'priority') cmp = a.priority - b.priority
      else if (sortKey === 'category') cmp = a.category.localeCompare(b.category)
      else if (sortKey === 'location_subject') cmp = a.location_subject.localeCompare(b.location_subject)
      return sortDir === 'desc' ? -cmp : cmp
    })

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <ChevronUp size={10} className="text-vsc-text/30" />
    return sortDir === 'asc' ? <ChevronUp size={10} /> : <ChevronDown size={10} />
  }

  return (
    <div>
      {/* Summary stats */}
      <div className="flex gap-4 mb-6">
        <div className="rounded-xl border border-vsc-border bg-vsc-panel px-6 py-4 min-w-[180px]">
          <p className="text-[10px] font-medium uppercase tracking-wider text-vsc-text/50">Total Open Flags</p>
          <p className="text-3xl font-bold text-vsc-text mt-1">{totalFlags}</p>
        </div>
        <div className={`rounded-xl border px-6 py-4 min-w-[180px] ${
          criticalCount > 0 ? 'border-red-800/50 bg-red-950/30' : 'border-vsc-border bg-vsc-panel'
        }`}>
          <p className="text-[10px] font-medium uppercase tracking-wider text-vsc-text/50">Critical Risks</p>
          <p className={`text-3xl font-bold mt-1 ${criticalCount > 0 ? 'text-red-400' : 'text-zinc-100'}`}>
            {criticalCount}
          </p>
        </div>
      </div>

      {/* Heat map */}
      <RiskHeatMap cells={heatMap} />

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4">
        <div className="flex-1 w-full">
          <h2 className="text-sm font-semibold text-vsc-text uppercase tracking-wider">
            System Flags & Recommendations
          </h2>
          <div className="flex items-center gap-2 mt-1">
            {analyzedAt && (
              <span className="text-[10px] text-vsc-text/40">Analyzed {timeAgo(analyzedAt)}</span>
            )}
            {onRefresh && (
              <button
                onClick={onRefresh}
                disabled={refreshing}
                className="flex items-center gap-1 text-[10px] text-vsc-text/40 hover:text-emerald-400 transition-colors disabled:opacity-40"
              >
                {refreshing ? <Loader2 size={9} className="animate-spin" /> : <RefreshCw size={9} />}
                Re-analyze
              </button>
            )}
          </div>
        </div>
        <div className="flex flex-col sm:flex-row gap-3 w-full sm:w-auto">
          <div className="relative w-full sm:w-auto">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search Flags..."
              className="pl-8 pr-3 py-1.5 rounded-lg border border-vsc-border bg-vsc-bg text-xs text-vsc-text placeholder-vsc-text/30 outline-none focus:border-vsc-text/40 w-full sm:w-48"
            />
          </div>
          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            className="rounded-lg border border-vsc-border bg-vsc-bg text-xs text-vsc-text px-3 py-1.5 outline-none focus:border-vsc-text/40 w-full sm:w-auto"
          >
            <option value="all">Priority: All</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-vsc-border overflow-x-auto">
        <table className="w-full text-xs min-w-[800px]">
          <thead>
            <tr className="bg-vsc-panel border-b border-vsc-border">
              <th
                onClick={() => toggleSort('priority')}
                className="text-left px-4 py-2.5 font-medium text-vsc-text/60 cursor-pointer hover:text-vsc-text w-20"
              >
                <span className="flex items-center gap-1">Priority <SortIcon col="priority" /></span>
              </th>
              <th
                onClick={() => toggleSort('category')}
                className="text-left px-4 py-2.5 font-medium text-vsc-text/60 cursor-pointer hover:text-vsc-text w-36"
              >
                <span className="flex items-center gap-1">Risk Category <SortIcon col="category" /></span>
              </th>
              <th
                onClick={() => toggleSort('location_subject')}
                className="text-left px-4 py-2.5 font-medium text-vsc-text/60 cursor-pointer hover:text-vsc-text w-40"
              >
                <span className="flex items-center gap-1">Location/Subject <SortIcon col="location_subject" /></span>
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-vsc-text/60">Flag Description</th>
              <th className="text-left px-4 py-2.5 font-medium text-vsc-text/60">Recommendation</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-vsc-text/40">
                  {search || priorityFilter !== 'all' ? 'No flags match your filters.' : 'No open flags. All clear.'}
                </td>
              </tr>
            )}
            {filtered.map((flag, idx) => {
              const isCriticalRow = flag.severity === 'critical' && flag.priority <= 3
              return (
                <tr
                  key={`${flag.source_type}-${flag.source_id}-${idx}`}
                  onClick={() => flag.link && navigate(flag.link)}
                  className={`border-b border-zinc-800/50 transition-colors ${
                    flag.link ? 'cursor-pointer' : ''
                  } ${
                    isCriticalRow
                      ? 'bg-gradient-to-r from-red-950/80 via-red-950/40 to-transparent hover:from-red-900/70'
                      : 'hover:bg-zinc-800/30'
                  }`}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-[11px] font-bold ${
                        isCriticalRow
                          ? 'bg-red-700 text-white'
                          : flag.severity === 'high'
                            ? 'bg-orange-800/60 text-orange-200'
                            : 'bg-zinc-800 text-zinc-400'
                      }`}>
                        {flag.priority}
                      </span>
                      {isCriticalRow && <AlertTriangle size={12} className="text-red-500" />}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`font-medium ${isCriticalRow ? 'text-red-300' : 'text-vsc-accent/75'}`}>
                      {flag.category}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-vsc-blue/70">{flag.location_subject}</td>
                  <td className="px-4 py-3 text-vsc-text/80 max-w-xs">{flag.description}</td>
                  <td className="px-4 py-3 text-vsc-text/50 max-w-sm">{flag.recommendation}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
