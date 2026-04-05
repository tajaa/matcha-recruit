import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, ChevronUp, ChevronDown, AlertTriangle } from 'lucide-react'
import type { DashboardFlag } from '../../types/dashboard'

interface Props {
  flags: DashboardFlag[]
  totalFlags: number
  criticalCount: number
}

type SortKey = 'priority' | 'category' | 'location_subject'
type SortDir = 'asc' | 'desc'

export function FlagsTable({ flags, totalFlags, criticalCount }: Props) {
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
    if (sortKey !== col) return <ChevronUp size={10} className="text-zinc-600" />
    return sortDir === 'asc' ? <ChevronUp size={10} /> : <ChevronDown size={10} />
  }

  return (
    <div>
      {/* Summary stats */}
      <div className="flex gap-4 mb-6">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 px-6 py-4 min-w-[180px]">
          <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-500">Total Open Flags</p>
          <p className="text-3xl font-bold text-zinc-100 mt-1">{totalFlags}</p>
        </div>
        <div className={`rounded-xl border px-6 py-4 min-w-[180px] ${
          criticalCount > 0 ? 'border-red-800/50 bg-red-950/30' : 'border-zinc-800 bg-zinc-900/50'
        }`}>
          <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-500">Critical Risks</p>
          <p className={`text-3xl font-bold mt-1 ${criticalCount > 0 ? 'text-red-400' : 'text-zinc-100'}`}>
            {criticalCount}
          </p>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-sm font-semibold text-zinc-100 uppercase tracking-wider flex-1">
          System Flags & Recommendations
        </h2>
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search Flags..."
            className="pl-8 pr-3 py-1.5 rounded-lg border border-zinc-700 bg-zinc-900 text-xs text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-500 w-48"
          />
        </div>
        <select
          value={priorityFilter}
          onChange={(e) => setPriorityFilter(e.target.value)}
          className="rounded-lg border border-zinc-700 bg-zinc-900 text-xs text-zinc-300 px-3 py-1.5 outline-none focus:border-zinc-500"
        >
          <option value="all">Priority: All</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-zinc-800 overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-zinc-900/80 border-b border-zinc-800">
              <th
                onClick={() => toggleSort('priority')}
                className="text-left px-4 py-2.5 font-medium text-zinc-400 cursor-pointer hover:text-zinc-200 w-20"
              >
                <span className="flex items-center gap-1">Priority <SortIcon col="priority" /></span>
              </th>
              <th
                onClick={() => toggleSort('category')}
                className="text-left px-4 py-2.5 font-medium text-zinc-400 cursor-pointer hover:text-zinc-200 w-36"
              >
                <span className="flex items-center gap-1">Risk Category <SortIcon col="category" /></span>
              </th>
              <th
                onClick={() => toggleSort('location_subject')}
                className="text-left px-4 py-2.5 font-medium text-zinc-400 cursor-pointer hover:text-zinc-200 w-40"
              >
                <span className="flex items-center gap-1">Location/Subject <SortIcon col="location_subject" /></span>
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400">Flag Description</th>
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400">Recommendation</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-zinc-500">
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
                      ? 'bg-gradient-to-r from-red-950/60 via-red-950/30 to-transparent hover:from-red-950/80'
                      : 'hover:bg-zinc-800/30'
                  }`}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className={`inline-flex items-center justify-center w-6 h-6 rounded-md text-[11px] font-bold ${
                        isCriticalRow
                          ? 'bg-red-600 text-white'
                          : flag.severity === 'high'
                            ? 'bg-orange-700/50 text-orange-300'
                            : 'bg-zinc-800 text-zinc-400'
                      }`}>
                        {flag.priority}
                      </span>
                      {isCriticalRow && <AlertTriangle size={12} className="text-red-400" />}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`font-medium ${isCriticalRow ? 'text-red-300' : 'text-zinc-200'}`}>
                      {flag.category}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-zinc-300">{flag.location_subject}</td>
                  <td className="px-4 py-3 text-zinc-300 max-w-xs">{flag.description}</td>
                  <td className="px-4 py-3 text-zinc-400 max-w-sm">{flag.recommendation}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
