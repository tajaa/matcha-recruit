/**
 * Companies gap-analysis overview — the landing dashboard tab.
 *
 * Master-admin triage: every analyzed company with its coverage, open gaps, and
 * drift (new locations since last analysis), searchable + sortable. Click a row
 * → that company's live gap dashboard. "Open any company" reaches un-analyzed
 * companies via the shared CompanyPicker.
 */
import { useMemo, useState } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useNavigate } from 'react-router-dom'
import { Loader2, Search, Building2, AlertTriangle, CheckCircle2, ChevronDown } from 'lucide-react'
import { adminOnboarding } from '../../api/admin/adminOnboarding'
import { CompanyPicker } from './AdminOnboarding'

type SortKey = 'attention' | 'name' | 'coverage' | 'gaps' | 'complexity'

function relDate(iso?: string | null): string {
  if (!iso) return '—'
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (d <= 0) return 'today'
  if (d === 1) return 'yesterday'
  if (d < 30) return `${d}d ago`
  return new Date(iso).toLocaleDateString()
}

export function complexityBandClass(band: string): string {
  switch (band) {
    case 'Severe': return 'bg-red-500/15 text-red-300 border-red-500/30'
    case 'High': return 'bg-amber-500/15 text-amber-300 border-amber-500/30'
    case 'Moderate': return 'bg-blue-500/15 text-blue-300 border-blue-500/30'
    default: return 'bg-zinc-700/40 text-zinc-300 border-zinc-600/40' // Low
  }
}

function StatCard({ label, value, tone }: { label: string; value: number | string; tone?: 'gap' | 'ok' }) {
  const color = tone === 'gap' ? 'text-amber-300' : tone === 'ok' ? 'text-emerald-300' : 'text-zinc-100'
  return (
    <div className="rounded-lg border border-vsc-border bg-vsc-panel p-3">
      <div className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${color}`}>{value}</div>
    </div>
  )
}

export default function GapOverview() {
  const navigate = useNavigate()
  const { data: rows, loading } = useAsync(() => adminOnboarding.getGapOverview(), [], [])
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<SortKey>('attention')
  const [pickerOpen, setPickerOpen] = useState(false)

  const view = useMemo(() => {
    const v = rows.filter((r) => (r.company_name || '').toLowerCase().includes(q.toLowerCase()))
    if (sort === 'name') return [...v].sort((a, b) => (a.company_name || '').localeCompare(b.company_name || ''))
    if (sort === 'coverage') return [...v].sort((a, b) => a.coverage_pct - b.coverage_pct)
    if (sort === 'gaps') return [...v].sort((a, b) => b.gaps - a.gaps)
    if (sort === 'complexity') return [...v].sort((a, b) => b.complexity - a.complexity)
    return v // 'attention' — server already sorts needs-attention-first
  }, [rows, q, sort])

  const totals = useMemo(() => {
    const openGaps = rows.reduce((s, r) => s + r.gaps, 0)
    const attention = rows.filter((r) => r.gaps > 0 || r.new_locations > 0).length
    const peakComplexity = rows.reduce((m, r) => Math.max(m, r.complexity), 0)
    return { companies: rows.length, openGaps, attention, peakComplexity }
  }, [rows])

  if (loading) {
    return <div className="flex items-center justify-center py-20 text-zinc-500"><Loader2 className="animate-spin" size={20} /></div>
  }

  return (
    <div>
      {/* Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <StatCard label="Companies analyzed" value={totals.companies} />
        <StatCard label="Open gaps (all)" value={totals.openGaps} tone={totals.openGaps > 0 ? 'gap' : 'ok'} />
        <StatCard label="Need attention" value={totals.attention} tone={totals.attention > 0 ? 'gap' : 'ok'} />
        <StatCard label="Peak complexity" value={totals.peakComplexity} tone={totals.peakComplexity >= 50 ? 'gap' : undefined} />
      </div>

      {/* Controls */}
      <div className="flex items-center gap-2 mb-3">
        <div className="relative flex-1 max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search companies…"
            className="w-full rounded-lg border border-vsc-border bg-vsc-bg pl-9 pr-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 outline-none focus:border-zinc-500"
          />
        </div>
        <div className="relative">
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className="appearance-none rounded-lg border border-vsc-border bg-vsc-bg pl-3 pr-8 py-2 text-sm text-zinc-200 outline-none focus:border-zinc-500"
          >
            <option value="attention">Needs attention</option>
            <option value="complexity">Highest complexity</option>
            <option value="gaps">Most gaps</option>
            <option value="coverage">Lowest coverage</option>
            <option value="name">Name (A–Z)</option>
          </select>
          <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none" />
        </div>
        <button
          onClick={() => setPickerOpen(true)}
          className="inline-flex items-center gap-2 px-3 h-9 rounded-lg border border-vsc-border hover:border-zinc-500 text-zinc-200 text-sm font-medium transition-colors"
        >
          <Building2 size={14} /> Open any company
        </button>
      </div>

      {/* Table */}
      {view.length === 0 ? (
        <div className="rounded-xl border border-vsc-border bg-vsc-panel p-10 text-center text-sm text-zinc-400">
          {rows.length === 0
            ? <>No companies analyzed yet. Use <span className="text-zinc-100">Open any company</span> or the <span className="text-zinc-100">Onboarding</span> tab to run the first analysis.</>
            : 'No companies match your search.'}
        </div>
      ) : (
        <div className="rounded-xl border border-vsc-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-vsc-panel text-[11px] uppercase tracking-wider text-zinc-500">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium">Company</th>
                <th className="text-left px-4 py-2.5 font-medium">Complexity</th>
                <th className="text-left px-4 py-2.5 font-medium w-44">Coverage</th>
                <th className="text-right px-4 py-2.5 font-medium">Covered</th>
                <th className="text-right px-4 py-2.5 font-medium">Gaps</th>
                <th className="text-left px-4 py-2.5 font-medium">Status</th>
                <th className="text-left px-4 py-2.5 font-medium">Analyzed</th>
              </tr>
            </thead>
            <tbody>
              {view.map((r) => (
                <tr
                  key={r.company_id}
                  onClick={() => navigate(`/admin/gap-analysis/company/${r.company_id}`)}
                  className="border-t border-vsc-border hover:bg-vsc-panel cursor-pointer"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-zinc-100">{r.company_name || '(unnamed)'}</div>
                    {r.new_locations > 0 && (
                      <span className="inline-flex items-center gap-1 mt-1 text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">
                        <AlertTriangle size={10} /> {r.new_locations} new location{r.new_locations > 1 ? 's' : ''}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border ${complexityBandClass(r.complexity_band)}`}>
                      <span className="text-sm font-semibold tabular-nums">{r.complexity}</span>
                      <span className="text-[10px] uppercase tracking-wide opacity-80">{r.complexity_band}</span>
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 rounded-full bg-vsc-bg overflow-hidden">
                        <div className={`h-full rounded-full ${r.coverage_pct >= 100 ? 'bg-emerald-500' : 'bg-amber-500'}`} style={{ width: `${r.coverage_pct}%` }} />
                      </div>
                      <span className="text-xs text-zinc-300 tabular-nums w-9 text-right">{r.coverage_pct}%</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right text-emerald-300 tabular-nums">{r.covered}</td>
                  <td className={`px-4 py-3 text-right tabular-nums font-medium ${r.gaps > 0 ? 'text-amber-300' : 'text-zinc-500'}`}>{r.gaps}</td>
                  <td className="px-4 py-3">
                    {r.gaps === 0 && r.new_locations === 0
                      ? <span className="inline-flex items-center gap-1 text-[11px] text-emerald-300"><CheckCircle2 size={12} /> Complete</span>
                      : <span className="text-[11px] text-amber-300">Needs attention</span>}
                  </td>
                  <td className="px-4 py-3 text-zinc-500 text-xs">{relDate(r.last_analyzed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pickerOpen && (
        <CompanyPicker
          onClose={() => setPickerOpen(false)}
          onPick={(id) => navigate(`/admin/gap-analysis/company/${id}`)}
        />
      )}
    </div>
  )
}
