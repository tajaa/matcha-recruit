import { Fragment, useEffect, useMemo, useState } from 'react'
import { X, ArrowUpDown, AlertTriangle } from 'lucide-react'
import type {
  EmployeeFlightRisk,
  FlightRiskLevel,
  FlightRiskWidgetSummary,
} from '../../types/dashboard'
import { fetchFlightRiskEmployees } from '../../api/dashboard'

interface Props {
  open: boolean
  onClose: () => void
  summary: FlightRiskWidgetSummary
}

type SortKey = 'score' | 'name' | 'top_factor'
type TierFilter = 'all' | 'flagged' | FlightRiskLevel

const TIER_STYLE: Record<FlightRiskLevel, { label: string; cls: string }> = {
  critical: { label: 'Critical', cls: 'bg-red-900/50 text-red-300 border-red-800/60' },
  high:     { label: 'High',     cls: 'bg-red-900/30 text-red-300 border-red-800/40' },
  elevated: { label: 'Elevated', cls: 'bg-amber-900/30 text-amber-300 border-amber-800/50' },
  low:      { label: 'Low',      cls: 'bg-emerald-900/30 text-emerald-300 border-emerald-800/50' },
}

const FACTOR_LABELS: Record<string, string> = {
  wage_gap: 'Wage gap',
  tenure: 'Tenure',
  er_case: 'ER case',
  ir_incident: 'IR incident',
  cohort: 'Cohort',
  manager: 'Manager',
}

export function FlightRiskDrawer({ open, onClose, summary }: Props) {
  const [rows, setRows] = useState<EmployeeFlightRisk[]>([])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('score')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [filter, setFilter] = useState<TierFilter>('flagged')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    setErr(null)
    fetchFlightRiskEmployees()
      .then((res) => setRows(res.employees))
      .catch((e) => setErr(e?.message || 'Failed to load detail'))
      .finally(() => setLoading(false))
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const filtered = useMemo(() => {
    let list = rows
    if (filter === 'flagged') list = list.filter((r) => r.tier === 'high' || r.tier === 'critical')
    else if (filter !== 'all') list = list.filter((r) => r.tier === filter)
    const dir = sortDir === 'asc' ? 1 : -1
    return [...list].sort((a, b) => {
      if (sortKey === 'name') return a.name.localeCompare(b.name) * dir
      if (sortKey === 'top_factor') return a.top_factor.localeCompare(b.top_factor) * dir
      return (a.score - b.score) * dir
    })
  }, [rows, filter, sortKey, sortDir])

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir(key === 'name' ? 'asc' : 'desc') }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full max-w-3xl h-full bg-zinc-950 border-l border-zinc-800 overflow-y-auto">
        <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b border-zinc-800 bg-zinc-950">
          <div>
            <h2 className="text-lg font-semibold text-zinc-100">Flight-Risk Detail</h2>
            <p className="text-xs text-zinc-500 mt-0.5">
              {summary.employees_evaluated} evaluated · {summary.critical_count + summary.high_count} flagged
              {summary.expected_loss_at_replacement > 0 && (
                <> · ${summary.expected_loss_at_replacement.toLocaleString()} max exposure</>
              )}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded hover:bg-zinc-900 text-zinc-400 hover:text-zinc-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="px-6 py-4 flex gap-1 flex-wrap text-xs">
          {(['flagged', 'all', 'critical', 'high', 'elevated', 'low'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2.5 py-1 rounded-md ${
                filter === f
                  ? 'bg-zinc-800 text-zinc-100'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900'
              }`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>

        <div className="px-6 pb-6">
          {err && (
            <p className="text-sm text-red-400 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4" />
              {err}
            </p>
          )}
          {loading ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-zinc-500">No employees match this filter.</p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-zinc-800">
              <table className="w-full text-sm text-left">
                <thead className="bg-zinc-900/60 text-zinc-400 text-xs uppercase tracking-wider">
                  <tr>
                    <th className="px-3 py-2 font-medium cursor-pointer" onClick={() => toggleSort('name')}>
                      <span className="inline-flex items-center gap-1">Name <ArrowUpDown className="h-3 w-3 opacity-50" /></span>
                    </th>
                    <th className="px-3 py-2 font-medium cursor-pointer" onClick={() => toggleSort('score')}>
                      <span className="inline-flex items-center gap-1">Score <ArrowUpDown className="h-3 w-3 opacity-50" /></span>
                    </th>
                    <th className="px-3 py-2 font-medium">Tier</th>
                    <th className="px-3 py-2 font-medium cursor-pointer" onClick={() => toggleSort('top_factor')}>
                      <span className="inline-flex items-center gap-1">Top driver <ArrowUpDown className="h-3 w-3 opacity-50" /></span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {filtered.map((r) => {
                    const expanded = expandedId === r.employee_id
                    const style = TIER_STYLE[r.tier]
                    return (
                      <Fragment key={r.employee_id}>
                        <tr
                          className="text-zinc-200 hover:bg-zinc-900/40 transition-colors cursor-pointer"
                          onClick={() => setExpandedId(expanded ? null : r.employee_id)}
                        >
                          <td className="px-3 py-2.5 font-medium">{r.name}</td>
                          <td className="px-3 py-2.5 tabular-nums">{r.score}</td>
                          <td className="px-3 py-2.5">
                            <span className={`inline-block text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border ${style.cls}`}>
                              {style.label}
                            </span>
                          </td>
                          <td className="px-3 py-2.5 text-zinc-400">
                            {FACTOR_LABELS[r.top_factor] ?? r.top_factor}
                          </td>
                        </tr>
                        {expanded && (
                          <tr className="bg-zinc-950/80">
                            <td colSpan={4} className="px-3 py-3">
                              <ul className="space-y-1.5">
                                {r.factors.map((f) => (
                                  <li key={f.name} className="flex items-start gap-3 text-xs">
                                    <span className={`mt-0.5 inline-block w-2 h-2 rounded-full ${
                                      f.color === 'red' ? 'bg-red-500' :
                                      f.color === 'yellow' ? 'bg-amber-500' : 'bg-emerald-600'
                                    }`} />
                                    <span className="text-zinc-400 w-20 shrink-0">
                                      {FACTOR_LABELS[f.name] ?? f.name}
                                    </span>
                                    <span className="text-zinc-500 w-12 shrink-0 tabular-nums">
                                      +{f.contribution}
                                    </span>
                                    <span className="text-zinc-300">{f.narrative}</span>
                                  </li>
                                ))}
                              </ul>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
