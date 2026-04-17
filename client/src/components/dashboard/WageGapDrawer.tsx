import { useEffect, useMemo, useState } from 'react'
import { X, Download, ArrowUpDown, TrendingDown, AlertTriangle } from 'lucide-react'
import type {
  EmployeeWageGapDetail,
  FlightRiskTier,
  RoleRollupItem,
  WageGapSummary,
} from '../../types/dashboard'
import { fetchWageGapDetails, downloadWageGapCsv } from '../../api/dashboard'

interface Props {
  open: boolean
  onClose: () => void
  summary: WageGapSummary
}

type SortKey = 'delta_percent' | 'delta_dollars' | 'annual_cost_p50' | 'pay_rate' | 'name'
type RiskFilter = 'all' | 'below' | FlightRiskTier

const RISK_STYLE: Record<FlightRiskTier, { label: string; cls: string }> = {
  high:   { label: 'High risk',   cls: 'bg-red-900/40 text-red-300 border-red-800/50' },
  medium: { label: 'Medium risk', cls: 'bg-amber-900/40 text-amber-300 border-amber-800/50' },
  low:    { label: 'Low risk',    cls: 'bg-yellow-900/30 text-yellow-300 border-yellow-800/50' },
  none:   { label: 'At market',   cls: 'bg-emerald-900/30 text-emerald-300 border-emerald-800/50' },
}

export function WageGapDrawer({ open, onClose, summary }: Props) {
  const [employees, setEmployees] = useState<EmployeeWageGapDetail[]>([])
  const [rollups, setRollups] = useState<RoleRollupItem[]>([])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('delta_percent')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [filter, setFilter] = useState<RiskFilter>('below')
  const [socFilter, setSocFilter] = useState<string>('all')

  useEffect(() => {
    if (!open) return
    setLoading(true)
    setErr(null)
    fetchWageGapDetails()
      .then((res) => {
        setEmployees(res.employees)
        setRollups(res.role_rollups)
      })
      .catch((e) => setErr(e?.message || 'Failed to load detail'))
      .finally(() => setLoading(false))
  }, [open])

  // Esc to close — expected drawer affordance.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const filtered = useMemo(() => {
    let list = employees
    if (socFilter !== 'all') list = list.filter((e) => e.soc_code === socFilter)
    if (filter === 'below') list = list.filter((e) => e.delta_percent <= -0.10)
    else if (filter !== 'all') list = list.filter((e) => e.flight_risk_tier === filter)
    const sorted = [...list].sort((a, b) => {
      let av: number | string = 0, bv: number | string = 0
      switch (sortKey) {
        case 'delta_percent':   av = a.delta_percent; bv = b.delta_percent; break
        case 'delta_dollars':   av = a.delta_dollars_per_hour; bv = b.delta_dollars_per_hour; break
        case 'annual_cost_p50': av = a.annual_cost_to_reach_p50; bv = b.annual_cost_to_reach_p50; break
        case 'pay_rate':        av = a.pay_rate; bv = b.pay_rate; break
        case 'name':            av = a.name.toLowerCase(); bv = b.name.toLowerCase(); break
      }
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })
    return sorted
  }, [employees, filter, socFilter, sortKey, sortDir])

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir(key === 'name' ? 'asc' : 'desc') }
  }

  const onExport = async () => {
    setExporting(true)
    try { await downloadWageGapCsv() }
    catch (e: any) { setErr(e?.message || 'Export failed') }
    finally { setExporting(false) }
  }

  if (!open) return null

  const totalLift = rollups.reduce((s, r) => s + r.total_annual_cost_to_lift_to_p50, 0)

  return (
    <div className="fixed inset-0 z-40 flex">
      {/* Scrim */}
      <div className="flex-1 bg-black/60" onClick={onClose} aria-hidden />

      {/* Panel */}
      <div className="w-full max-w-5xl bg-zinc-950 border-l border-zinc-800/70 shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 px-6 py-5 border-b border-zinc-800/60">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-500">
              Wage Gap — Action List
            </p>
            <h2 className="text-xl font-semibold text-zinc-100 mt-1">
              {summary.employees_below_market} of {summary.employees_evaluated} employees below market
            </h2>
            <p className="text-xs text-zinc-500 mt-1">
              Source: BLS OEWS 2024Q4 · $5,864 replacement-cost anchor (Restroworks 2024)
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onExport}
              disabled={exporting || filtered.length === 0}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-matcha-600/80 hover:bg-matcha-600 text-white disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Download className="h-3.5 w-3.5" />
              {exporting ? 'Exporting...' : 'Export CSV'}
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-md hover:bg-zinc-800 text-zinc-500 hover:text-zinc-200"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Role rollups */}
        {rollups.length > 0 && (
          <div className="px-6 pt-5 pb-3 border-b border-zinc-800/60 bg-zinc-900/40">
            <div className="flex items-center justify-between mb-2.5">
              <p className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
                By Role · click to filter
              </p>
              <p className="text-[11px] text-zinc-500">
                Total lift to p50: <span className="text-amber-300 font-semibold">${totalLift.toLocaleString()}/yr</span>
              </p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
              {rollups.map((r) => {
                const active = socFilter === r.soc_code
                const deltaPct = Math.round(r.median_delta_percent * 100)
                return (
                  <button
                    key={r.soc_code}
                    onClick={() => setSocFilter(active ? 'all' : r.soc_code)}
                    className={`text-left p-3 rounded-lg border transition-colors ${
                      active
                        ? 'border-matcha-500/60 bg-matcha-900/20'
                        : 'border-zinc-800/60 bg-zinc-900/50 hover:border-zinc-700'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-xs font-medium text-zinc-200 leading-tight">
                        {r.soc_label}
                      </p>
                      <span className="text-[10px] text-zinc-500 font-mono shrink-0">{r.soc_code}</span>
                    </div>
                    <div className="flex items-baseline gap-2 mt-2">
                      <span className="text-lg font-semibold text-zinc-100 tabular-nums">
                        {r.below_market_count}
                      </span>
                      <span className="text-[11px] text-zinc-500">
                        of {r.headcount} below · median {deltaPct >= 0 ? '+' : ''}{deltaPct}%
                      </span>
                    </div>
                    {r.total_annual_cost_to_lift_to_p50 > 0 && (
                      <p className="text-[11px] text-amber-400/90 mt-1">
                        ${r.total_annual_cost_to_lift_to_p50.toLocaleString()}/yr to reach p50
                      </p>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* Filter bar */}
        <div className="px-6 py-3 border-b border-zinc-800/60 flex items-center gap-2 flex-wrap">
          <span className="text-[11px] uppercase tracking-wider text-zinc-500 mr-1">Show:</span>
          {(['below', 'high', 'medium', 'low', 'none', 'all'] as const).map((k) => (
            <button
              key={k}
              onClick={() => setFilter(k)}
              className={`px-2.5 py-1 rounded text-[11px] font-medium border ${
                filter === k
                  ? 'bg-zinc-700 text-zinc-100 border-zinc-600'
                  : 'bg-zinc-900 text-zinc-400 border-zinc-800 hover:text-zinc-200'
              }`}
            >
              {k === 'all' ? 'All' : k === 'below' ? 'Below market' : RISK_STYLE[k].label}
            </button>
          ))}
          {socFilter !== 'all' && (
            <button
              onClick={() => setSocFilter('all')}
              className="ml-auto px-2.5 py-1 rounded text-[11px] text-zinc-400 hover:text-zinc-200 border border-zinc-800 bg-zinc-900"
            >
              Clear role filter
            </button>
          )}
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="p-10 text-center text-sm text-zinc-500">Loading...</div>
          ) : err ? (
            <div className="p-10 flex items-center justify-center gap-2 text-sm text-red-400">
              <AlertTriangle className="h-4 w-4" />
              {err}
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-10 text-center">
              <TrendingDown className="h-8 w-8 text-zinc-700 mx-auto mb-2" />
              <p className="text-sm text-zinc-500">No employees match these filters.</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-zinc-950 border-b border-zinc-800/60 z-10">
                <tr className="text-[10px] uppercase tracking-wider text-zinc-500">
                  <SortHeader label="Employee"     active={sortKey === 'name'}            dir={sortDir} onClick={() => toggleSort('name')} />
                  <th className="text-left font-medium px-3 py-2">Role / Location</th>
                  <SortHeader label="Pay"          active={sortKey === 'pay_rate'}        dir={sortDir} onClick={() => toggleSort('pay_rate')} align="right" />
                  <th className="text-right font-medium px-3 py-2">Market p50</th>
                  <SortHeader label="Δ / hr"       active={sortKey === 'delta_dollars'}   dir={sortDir} onClick={() => toggleSort('delta_dollars')} align="right" />
                  <SortHeader label="Δ %"          active={sortKey === 'delta_percent'}   dir={sortDir} onClick={() => toggleSort('delta_percent')} align="right" />
                  <SortHeader label="Lift to p50/yr" active={sortKey === 'annual_cost_p50'} dir={sortDir} onClick={() => toggleSort('annual_cost_p50')} align="right" />
                  <th className="text-left font-medium px-3 py-2">Risk</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((e) => {
                  const deltaPct = Math.round(e.delta_percent * 100)
                  const risk = RISK_STYLE[e.flight_risk_tier]
                  return (
                    <tr key={e.employee_id} className="border-b border-zinc-900 hover:bg-zinc-900/50">
                      <td className="px-3 py-2.5 text-zinc-200">{e.name}</td>
                      <td className="px-3 py-2.5 text-zinc-400 text-xs">
                        <div>{e.job_title}</div>
                        <div className="text-zinc-600">
                          {e.work_city ? `${e.work_city}, ${e.work_state}` : e.work_state}
                          <span className="ml-1.5 text-[9px] uppercase tracking-wider">
                            · {e.benchmark_tier}
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-right text-zinc-200 tabular-nums">
                        ${e.pay_rate.toFixed(2)}
                      </td>
                      <td className="px-3 py-2.5 text-right text-zinc-500 tabular-nums">
                        ${e.market_p50.toFixed(2)}
                      </td>
                      <td className={`px-3 py-2.5 text-right tabular-nums ${
                        e.delta_dollars_per_hour < 0 ? 'text-amber-400' : 'text-emerald-400'
                      }`}>
                        {e.delta_dollars_per_hour >= 0 ? '+' : ''}${e.delta_dollars_per_hour.toFixed(2)}
                      </td>
                      <td className={`px-3 py-2.5 text-right tabular-nums font-medium ${
                        deltaPct < 0 ? 'text-amber-400' : 'text-emerald-400'
                      }`}>
                        {deltaPct >= 0 ? '+' : ''}{deltaPct}%
                      </td>
                      <td className="px-3 py-2.5 text-right text-zinc-300 tabular-nums">
                        {e.annual_cost_to_reach_p50 > 0
                          ? `$${e.annual_cost_to_reach_p50.toLocaleString()}`
                          : <span className="text-zinc-700">—</span>}
                      </td>
                      <td className="px-3 py-2.5">
                        <span className={`inline-flex px-2 py-0.5 rounded text-[10px] font-medium border ${risk.cls}`}>
                          {risk.label}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer count */}
        {!loading && !err && (
          <div className="px-6 py-2.5 border-t border-zinc-800/60 text-[11px] text-zinc-500">
            Showing <span className="text-zinc-300">{filtered.length}</span> of {employees.length} evaluated employees
            {summary.employees_unclassified > 0 && (
              <span className="ml-3 text-zinc-600">
                · {summary.employees_unclassified} unclassified (add SOC mapping to include)
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function SortHeader({
  label, active, onClick, align = 'left',
}: { label: string; active: boolean; dir: 'asc' | 'desc'; onClick: () => void; align?: 'left' | 'right' }) {
  return (
    <th className={`font-medium px-3 py-2 ${align === 'right' ? 'text-right' : 'text-left'}`}>
      <button
        onClick={onClick}
        className={`inline-flex items-center gap-1 uppercase tracking-wider ${
          active ? 'text-zinc-200' : 'text-zinc-500 hover:text-zinc-300'
        }`}
      >
        {label}
        <ArrowUpDown className={`h-2.5 w-2.5 ${active ? 'opacity-100' : 'opacity-30'}`} />
      </button>
    </th>
  )
}
