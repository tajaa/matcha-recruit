import { useEffect, useState, useCallback } from 'react'
import { api } from '../../../api/client'
import { Badge } from '../../ui'
import { CATEGORY_LABELS } from '../../../generated/complianceCategories'
import { ExternalLink, AlertTriangle, Shield, Loader2 } from 'lucide-react'

type CoverageStat = { category: string; total: number; has_penalty: number; pct: number }
type PenaltyDetail = {
  category: string; title: string; enforcing_agency: string | null
  penalty_min: string | null; penalty_max: string | null; per_violation: string | null
  annual_cap: string | null; criminal: string | null; summary: string | null
  source_url: string | null; verified_date: string | null
}
type TopPenalty = {
  category: string; title: string; jurisdiction: string
  max_penalty: number | null; summary: string | null; enforcing_agency: string | null
}
type PenaltyData = { coverage: CoverageStat[]; details: PenaltyDetail[]; top_penalties: TopPenalty[] }

function fmtUsd(n: number | null) {
  if (n == null) return '—'
  return n >= 1_000_000
    ? `$${(n / 1_000_000).toFixed(1)}M`
    : n >= 1_000
      ? `$${(n / 1_000).toFixed(0)}K`
      : `$${n.toLocaleString()}`
}

function catLabel(cat: string) {
  return CATEGORY_LABELS[cat] ?? cat.replace(/_/g, ' ')
}

export default function PenaltyOverviewTab() {
  const [data, setData] = useState<PenaltyData | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandedCat, setExpandedCat] = useState<string | null>(null)
  const [view, setView] = useState<'coverage' | 'details' | 'top'>('details')

  const fetch = useCallback(async () => {
    setLoading(true)
    try { setData(await api.get<PenaltyData>('/admin/jurisdictions/penalty-overview')) }
    catch { setData(null) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetch() }, [fetch])

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="animate-spin text-zinc-500" size={20} /></div>
  if (!data) return <div className="text-center py-12 text-zinc-500 text-sm">Failed to load penalty data</div>

  const totalReqs = data.coverage.reduce((s, c) => s + c.total, 0)
  const totalWithPenalty = data.coverage.reduce((s, c) => s + c.has_penalty, 0)
  const overallPct = totalReqs > 0 ? Math.round(totalWithPenalty / totalReqs * 100) : 0

  return (
    <div className="space-y-4">
      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
          <p className="text-[10px] text-zinc-500 uppercase tracking-wide">Coverage</p>
          <p className="text-xl font-semibold text-zinc-100">{overallPct}%</p>
          <p className="text-xs text-zinc-500">{totalWithPenalty.toLocaleString()} / {totalReqs.toLocaleString()} requirements</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
          <p className="text-[10px] text-zinc-500 uppercase tracking-wide">Categories</p>
          <p className="text-xl font-semibold text-zinc-100">{data.details.length}</p>
          <p className="text-xs text-zinc-500">with penalty data</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
          <p className="text-[10px] text-zinc-500 uppercase tracking-wide">Highest Penalty</p>
          <p className="text-xl font-semibold text-red-400">
            {data.top_penalties[0] ? fmtUsd(data.top_penalties[0].max_penalty) : '—'}
          </p>
          <p className="text-xs text-zinc-500">{data.top_penalties[0]?.category.replace(/_/g, ' ') ?? ''}</p>
        </div>
      </div>

      {/* View toggle */}
      <div className="flex gap-1.5">
        {(['details', 'coverage', 'top'] as const).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`px-3 py-1.5 text-xs rounded transition-colors ${
              view === v ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {v === 'details' ? 'By Category' : v === 'coverage' ? 'Coverage' : 'Highest Penalties'}
          </button>
        ))}
      </div>

      {/* Details view — penalty info per category */}
      {view === 'details' && (
        <div className="space-y-1">
          {data.details.map((d) => (
            <div key={d.category} className="border border-zinc-800 rounded-lg overflow-hidden">
              <button
                onClick={() => setExpandedCat(expandedCat === d.category ? null : d.category)}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-zinc-800/50 transition-colors"
              >
                <Shield size={14} className="text-red-400/70 shrink-0" />
                <span className="text-sm font-medium text-zinc-200 flex-1">{catLabel(d.category)}</span>
                <span className="text-xs text-zinc-500">{d.enforcing_agency}</span>
                {d.summary && (
                  <span className="text-xs text-red-400/70 max-w-[300px] truncate">{d.summary}</span>
                )}
              </button>
              {expandedCat === d.category && (
                <div className="px-4 pb-3 pt-1 border-t border-zinc-800/60 space-y-2">
                  {d.summary && (
                    <div className="text-sm text-red-300 bg-red-900/15 border border-red-800/30 rounded px-3 py-2">
                      {d.summary}
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs">
                    <div>
                      <span className="text-zinc-500">Enforcing Agency: </span>
                      <span className="text-zinc-300">{d.enforcing_agency ?? '—'}</span>
                    </div>
                    <div>
                      <span className="text-zinc-500">Per Violation: </span>
                      <span className="text-zinc-300">{d.per_violation === 'true' ? 'Yes' : 'No / Aggregate'}</span>
                    </div>
                    <div>
                      <span className="text-zinc-500">Civil Min: </span>
                      <span className="text-zinc-300">{d.penalty_min ? `$${Number(d.penalty_min).toLocaleString()}` : '—'}</span>
                    </div>
                    <div>
                      <span className="text-zinc-500">Civil Max: </span>
                      <span className="text-zinc-300">{d.penalty_max ? `$${Number(d.penalty_max).toLocaleString()}` : '—'}</span>
                    </div>
                    <div>
                      <span className="text-zinc-500">Annual Cap: </span>
                      <span className="text-zinc-300">{d.annual_cap && d.annual_cap !== 'null' ? `$${Number(d.annual_cap).toLocaleString()}` : 'None'}</span>
                    </div>
                    <div>
                      <span className="text-zinc-500">Verified: </span>
                      <span className="text-zinc-300">{d.verified_date ?? '—'}</span>
                    </div>
                  </div>
                  {d.criminal && (
                    <div className="text-xs">
                      <span className="text-zinc-500">Criminal: </span>
                      <span className="text-zinc-400">{d.criminal}</span>
                    </div>
                  )}
                  {d.source_url && (
                    <a
                      href={d.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-cyan-500 hover:text-cyan-400"
                    >
                      <ExternalLink size={10} />
                      Source
                    </a>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Coverage view */}
      {view === 'coverage' && (
        <div className="overflow-hidden rounded-lg border border-zinc-800">
          <table className="w-full text-xs">
            <thead className="bg-zinc-900/50 text-zinc-400">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Category</th>
                <th className="px-3 py-2 text-right font-medium">Total</th>
                <th className="px-3 py-2 text-right font-medium">With Penalty</th>
                <th className="px-3 py-2 text-right font-medium">Coverage</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {data.coverage.map((c) => (
                <tr key={c.category} className="text-zinc-300">
                  <td className="px-3 py-1.5">{catLabel(c.category)}</td>
                  <td className="px-3 py-1.5 text-right text-zinc-500">{c.total}</td>
                  <td className="px-3 py-1.5 text-right">{c.has_penalty}</td>
                  <td className="px-3 py-1.5 text-right">
                    <Badge variant={c.pct === 100 ? 'success' : c.pct > 0 ? 'warning' : 'danger'}>
                      {c.pct}%
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Top penalties view */}
      {view === 'top' && (
        <div className="space-y-1.5">
          {data.top_penalties.map((p, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-2 border border-zinc-800 rounded-lg">
              <div className="flex items-center justify-center w-6 h-6 rounded-full bg-red-900/30 text-red-400 text-[10px] font-bold shrink-0">
                {i + 1}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-zinc-200 truncate">{catLabel(p.category)}</p>
                <p className="text-xs text-zinc-500 truncate">{p.enforcing_agency} — {p.jurisdiction}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-sm font-semibold text-red-400">{fmtUsd(p.max_penalty)}</p>
                <p className="text-[10px] text-zinc-500">max per violation</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
